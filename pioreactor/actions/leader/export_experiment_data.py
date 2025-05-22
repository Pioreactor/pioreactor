# -*- coding: utf-8 -*-
# export experiment data
# See create_tables.sql for all tables
from __future__ import annotations

import sys
from base64 import b64decode
from contextlib import closing
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from msgspec import DecodeError
from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode

from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.structs import Dataset


def source_exists(cursor, table_name_to_check: str) -> bool:
    query = "SELECT 1 FROM sqlite_master WHERE (type='table' or type='view') and name = ?"
    return cursor.execute(query, (table_name_to_check,)).fetchone() is not None


def generate_timestamp_to_localtimestamp_clause(timestamp_columns: list[str]) -> str:
    if not timestamp_columns:
        return ""

    clause = ",".join([f"datetime(T.{c}, 'localtime') as {c}_localtime" for c in timestamp_columns])

    return clause


def generate_timestamp_to_relative_time_clause(default_order_by: str) -> str:
    if not default_order_by:
        return ""

    START_TIME = "E.created_at"

    clause = (
        f"(unixepoch({default_order_by}) - unixepoch({START_TIME}))/3600.0 as hours_since_experiment_created"
    )

    return clause


def load_exportable_datasets() -> dict[str, Dataset]:
    builtins = sorted(Path("/home/pioreactor/.pioreactor/exportable_datasets").glob("*.y*ml"))
    plugins = sorted(Path("/home/pioreactor/.pioreactor/plugins/exportable_datasets").glob("*.y*ml"))
    parsed_yaml = {}
    for file in builtins + plugins:
        try:
            dataset = yaml_decode(file.read_bytes(), type=Dataset)
            parsed_yaml[dataset.dataset_name] = dataset
        except (ValidationError, DecodeError) as e:
            click.echo(f"Yaml error in {Path(file).name}: {e}")

    return parsed_yaml


def decode_base64(string: str) -> str:
    return b64decode(string).decode("utf-8")


def validate_dataset_information(dataset: Dataset, cursor) -> None:
    if not (dataset.table or dataset.query):
        raise ValueError("query or table must be defined.")

    if dataset.table:
        table = dataset.table
        if not source_exists(cursor, table):
            raise ValueError(f"Table {table} does not exist.")


def create_experiment_clause(
    experiments: list[str], existing_placeholders: dict[str, str]
) -> tuple[str, dict[str, str]]:
    if not experiments:  # Simplified check for an empty list
        return "TRUE", existing_placeholders
    else:
        quoted_experiments = ", ".join(f":experiment{i}" for i in range(len(experiments)))
        existing_placeholders = existing_placeholders | {
            f"experiment{i}": experiment for i, experiment in enumerate(experiments)
        }
        return f"T.experiment IN ({quoted_experiments})", existing_placeholders


def create_timespan_clause(
    start_time: str | None, end_time: str | None, time_column: str, existing_placeholders: dict[str, str]
) -> tuple[str, dict[str, str]]:
    if start_time is not None and end_time is not None:
        existing_placeholders["start_time"] = start_time
        existing_placeholders["end_time"] = end_time
        return f"T.{time_column} >= :start_time AND {time_column} <= :end_time", existing_placeholders

    elif start_time is not None:
        existing_placeholders["start_time"] = start_time
        return f"T.{time_column} >= :start_time", existing_placeholders

    elif end_time is not None:
        existing_placeholders["end_time"] = end_time
        return f"T.{time_column} <= :end_time", existing_placeholders
    else:
        raise ValueError


def create_sql_query(
    selects: list[str],
    table_or_subquery: str,
    existing_placeholders: dict[str, str],
    where_clauses: list[str] | None = None,
    order_by_col: str | None = None,
    has_experiment: bool = False,
) -> tuple[str, dict[str, str]]:
    """
    Constructs an SQL query with SELECT, FROM, WHERE, and ORDER BY clauses.
    """
    # Base SELECT and FROM clause
    query = f"SELECT {', '.join(selects)} FROM ({table_or_subquery}) T"

    if has_experiment:
        query += " JOIN experiments E ON E.experiment = T.experiment"

    # Add WHERE clause if provided
    if where_clauses:
        query += f" WHERE {' AND '.join(where_clauses)}"

    # Add ORDER BY clause if provided
    if order_by_col:
        query += f' ORDER BY "T.{order_by_col}"'

    return query, existing_placeholders


def export_experiment_data(
    experiments: list[str],
    dataset_names: list[str],
    output: str,
    start_time: str | None = None,
    end_time: str | None = None,
    partition_by_unit: bool = False,
    partition_by_experiment: bool = True,
) -> None:
    """
    Set an experiment, else it defaults to the entire table.
    """
    import sqlite3
    import zipfile
    import csv

    if not output.endswith(".zip"):
        click.echo("output should end with .zip")
        sys.exit(1)

    if len(dataset_names) == 0:
        click.echo("At least one dataset name must be provided.")
        sys.exit(1)

    logger = create_logger("export_experiment_data", experiment="$experiment")
    logger.info(
        f"Starting export of dataset{'s' if len(dataset_names) > 1 else ''}: {', '.join(dataset_names)}."
    )

    time = datetime.now().strftime("%Y%m%d%H%M%S")

    available_datasets = load_exportable_datasets()

    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf, closing(
        sqlite3.connect(f"file:{config.get('storage', 'database')}?mode=ro", uri=True)
    ) as con:
        con.create_function(
            "BASE64", 1, decode_base64
        )  # TODO: until next OS release which implements a native sqlite3 base64 function

        cursor = con.cursor()
        cursor.executescript(
            """
            PRAGMA busy_timeout = 15000;
            PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
            PRAGMA temp_store = 2;  -- stop writing small files to disk, use mem
            PRAGMA foreign_keys = ON;
            PRAGMA cache_size = -4000;
        """
        )
        con.set_trace_callback(logger.debug)

        for dataset_name in dataset_names:
            try:
                dataset = available_datasets[dataset_name]
            except KeyError:
                logger.warning(
                    f"Dataset `{dataset_name}` is not found as an available exportable dataset. A yaml file needs to be added to ~/.pioreactor/exportable_datasets. Skipping. Available datasets are {list(available_datasets.keys())}",
                )
                continue

            validate_dataset_information(dataset, cursor)

            _partition_by_unit = dataset.has_unit and (partition_by_unit or dataset.always_partition_by_unit)
            _partition_by_experiment = dataset.has_experiment and partition_by_experiment
            path_to_files: list[Path] = []
            placeholders: dict[str, str] = {}

            order_by_col = dataset.default_order_by
            table_or_subquery = dataset.table or dataset.query
            assert table_or_subquery is not None

            where_clauses: list[str] = []
            selects = ["T.*"]

            if dataset.timestamp_columns:
                selects.append(generate_timestamp_to_localtimestamp_clause(dataset.timestamp_columns))

            if dataset.has_experiment:
                experiment_clause, placeholders = create_experiment_clause(experiments, placeholders)
                where_clauses.append(experiment_clause)

            if dataset.has_experiment and dataset.default_order_by:
                selects.append(generate_timestamp_to_relative_time_clause(dataset.default_order_by))

            if dataset.timestamp_columns and (start_time or end_time):
                assert dataset.default_order_by is not None
                timespan_clause, placeholders = create_timespan_clause(
                    start_time, end_time, dataset.default_order_by, placeholders
                )
                where_clauses.append(timespan_clause)

            query, placeholders = create_sql_query(
                selects, table_or_subquery, placeholders, where_clauses, order_by_col, dataset.has_experiment
            )
            cursor.execute(query, placeholders)

            headers = [_[0] for _ in cursor.description]

            if _partition_by_experiment:
                try:
                    iloc_experiment = headers.index("experiment")
                except ValueError:
                    iloc_experiment = None
            else:
                iloc_experiment = None

            if _partition_by_unit:
                try:
                    iloc_unit = headers.index("pioreactor_unit")
                except ValueError:
                    iloc_unit = None
            else:
                iloc_unit = None

            parition_to_writer_map: dict[tuple, Any] = {}
            count = 0
            with ExitStack() as stack:
                for row in cursor:
                    count += 1
                    rows_partition = (
                        row[iloc_experiment] if iloc_experiment is not None else "all_experiments",
                        row[iloc_unit] if iloc_unit is not None else "all_units",
                    )

                    if rows_partition not in parition_to_writer_map:
                        # create a new csv writer for this partition since it doesn't exist yet
                        filename = f"{dataset_name}-" + "-".join(rows_partition) + f"-{time}.csv"
                        filename = filename.replace(" ", "_")
                        path_to_file = Path(output).parent / filename
                        parition_to_writer_map[rows_partition] = csv.writer(
                            stack.enter_context(open(path_to_file, "w")), delimiter=","
                        )
                        parition_to_writer_map[rows_partition].writerow(headers)

                        path_to_files.append(path_to_file)

                    parition_to_writer_map[rows_partition].writerow(row)

                    if count % 10_000 == 0:
                        logger.debug(f"Exported {count} rows...")

            logger.debug(f"Exported {count} rows from {dataset_name}.")
            if count == 0:
                logger.warning(f"No data present in {dataset_name}. Check database?")

            zf.mkdir(dataset_name)
            for path_to_file in path_to_files:
                zf.write(path_to_file, arcname=f"{dataset_name}/{path_to_file.name}")
                path_to_file.unlink()

    logger.info("Finished export.")
    return


@click.command(name="export_experiment_data")
@click.option("--experiment", multiple=True, default=[])
@click.option("--output", default="./output.zip")
@click.option("--partition-by-unit", is_flag=True)
@click.option("--partition-by-experiment", is_flag=True)
@click.option("--dataset-name", multiple=True, default=[])
@click.option("--start-time", help="iso8601")
@click.option("--end-time", help="iso8601")
def click_export_experiment_data(
    experiment, output, partition_by_unit, partition_by_experiment, dataset_name, start_time, end_time
):
    """
    (leader only) Export datasets from db.
    """
    export_experiment_data(
        experiment, dataset_name, output, start_time, end_time, partition_by_unit, partition_by_experiment
    )
