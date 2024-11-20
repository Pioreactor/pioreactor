# -*- coding: utf-8 -*-
# export experiment data
# See create_tables.sql for all tables
from __future__ import annotations

from contextlib import closing
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.structs import Dataset


def is_valid_table_name(table_name: str) -> bool:
    import re

    return bool(re.fullmatch(r"^[a-zA-Z]\w*$", table_name))


def source_exists(cursor, table_name_to_check: str) -> bool:
    query = "SELECT 1 FROM sqlite_master WHERE (type='table' or type='view') and name = ?"
    return cursor.execute(query, (table_name_to_check,)).fetchone() is not None


def get_column_names(cursor, table_name: str) -> list[str]:
    query = f"PRAGMA table_info({table_name})"
    return [row[1] for row in cursor.execute(query).fetchall()]


def filter_to_timestamp_columns(column_names: list[str]) -> list[str]:
    # We use a standard here: `timestamp` or ends in `_at`
    return [c for c in column_names if (c == "timestamp") or c.endswith("_at")]


def generate_timestamp_to_localtimestamp_clause(timestamp_columns) -> str:

    if not timestamp_columns:
        return ""

    clause = ",".join([f"datetime({c}, 'localtime') as {c}_localtime" for c in timestamp_columns])

    return clause


def load_exportable_datasets() -> list[Dataset]:
    builtins = sorted(Path("/home/pioreactor/.pioreactor/exportable_datasets").glob("*.y*ml"))
    plugins = sorted(Path("/home/pioreactor/.pioreactor/plugins/exportable_datasets").glob("*.y*ml"))
    parsed_yaml = {}
    for file in (builtins + plugins):
        try:
            dataset = yaml_decode(file.read_bytes(), type=Dataset)
            parsed_yaml[dataset.dataset_name] = dataset
        except (ValidationError, DecodeError) as e:
            click.echo(
                f"Yaml error in {Path(file).name}: {e}"
            )

    return parsed_yaml


def validate_dataset_information(dataset: Dataset, cursor):
    if not (dataset.table or dataset.query):
        raise ValueError("query or table must be defined.")

    if dataset.table:
        table = dataset.table
        if not source_exists(cursor, table)
            raise ValueError(f"Table {table} does not exist.")

def export_dataset(dataset):
    pass

def create_experiment_clause(experiments: list[str], existing_placeholders: dict[str, str]) -> tuple[str, dict[str, str]]:
    if not experiments:  # Simplified check for an empty list
        return "TRUE"
    else:
        quoted_experiments = ", ".join(f":experiment{i}" for i in range(experiments))
        existing_placeholders = existing_placeholders | {f":experiment{i}": experiment for i, experiment in enumerate(experiments)}
        return f"experiment IN ({quoted_experiments})", existing_placeholders


def create_sql_query(
    selects: list[str],
    table_or_subquery: str,
    existing_placeholders: dict[str, str],
    where_clauses: list[str] | None = None,
    order_by: str | None = None,
) -> str, dict[str, str]:
    """
    Constructs an SQL query with SELECT, FROM, WHERE, and ORDER BY clauses.
    """
    # Base SELECT and FROM clause
    query = f"SELECT {', '.join(selects)} FROM {table_or_subquery}"

    # Add WHERE clause if provided
    if where_clauses:
        query += f" WHERE {' AND '.join(where_clauses)}"

    # Add ORDER BY clause if provided
    if order_by:
        query += f" ORDER BY :order_by"
        existing_placeholders['order_by'] = order_by

    return query, existing_placeholders



def export_experiment_data(
    experiments: list[str], dataset_names: list[str], output: str, partition_by_unit: bool = False,
) -> None:
    """
    Set an experiment, else it defaults to the entire table.
    """
    import sqlite3
    import zipfile
    import csv

    if not output.endswith(".zip"):
        click.echo("output should end with .zip")
        raise click.Abort()

    logger = create_logger("export_experiment_data")
    logger.info(f"Starting export of dataset{'s' if len(dataset_names) > 1 else ''}: {', '.join(dataset_names)}.")

    time = datetime.now().strftime("%Y%m%d%H%M%S")

    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf, closing(
        sqlite3.connect(config["storage"]["database"])
    ) as con:
        cursor = con.cursor()

        for dataset in dataset_names:

            validate_dataset_information(dataset)


            placeholders: dict[str, str] = {}
            timestamp_to_localtimestamp_clause = generate_timestamp_to_localtimestamp_clause(dataset.timestamp_columns)
            order_by = dataset.default_order_by
            table_or_subquery = dataset.table or dataset.query

            where_clauses: list[str] = []
            selects = ["*", timestamp_to_localtimestamp_clause]

            if dataset.has_experiment:
               experiment_clause, placeholders = create_experiment_clause(experiments, placeholders)
               where_clauses.append(experiment_clause)

            query, placeholders = create_sql_query(selects, table_or_subquery, placeholders, where_clauses, order_by)

            cursor.execute(query, placeholders)


            _partition_by_unit = partition_by_unit
            if table in ("pioreactor_unit_activity_data", "pioreactor_unit_activity_data_rollup"):
                _partition_by_unit = True

            if not _partition_by_unit:

                filename = filename.replace(" ", "_")
                path_to_file = os.path.join(os.path.dirname(output), filename)
                with open(path_to_file, "w") as csv_file:
                    csv_writer = csv.writer(csv_file, delimiter=",")
                    csv_writer.writerow([_[0] for _ in cursor.description])
                    csv_writer.writerows(cursor)

                zf.write(path_to_file, arcname=filename)
                Path(path_to_file).unlink() # rm file


            else:
                headers = [_[0] for _ in cursor.description]
                if "pioreactor_unit" in headers:
                    iloc_pioreactor_unit = headers.index("pioreactor_unit")
                else:
                    logger.debug(f"pioreactor_unit not found in {table}, skipping partition.")
                    iloc_pioreactor_unit = None

                filenames = []
                unit_to_writer_map = {}

                with ExitStack() as stack:
                    for row in cursor:
                        if iloc_pioreactor_unit:
                            unit = row[iloc_pioreactor_unit]
                        else:
                            unit = "all"

                        if unit not in unit_to_writer_map:
                            filename = f"{experiment or 'exp'}-{table}-{unit}-{time}.csv"
                            filenames.append(filename)
                            path_to_file = os.path.join(os.path.dirname(output), filename)
                            unit_to_writer_map[unit] = csv.writer(
                                stack.enter_context(open(path_to_file, "w")), delimiter=","
                            )
                            unit_to_writer_map[unit].writerow(headers)

                        unit_to_writer_map[unit].writerow(row)

                for filename in filenames:
                    path_to_file = os.path.join(os.path.dirname(output), filename)
                    zf.write(path_to_file, arcname=filename)
                    Path(path_to_file).unlink()

    logger.info("Finished export.")
    return


@click.command(name="export_experiment_data")
@click.option("--experiment", multiple=True, default=[])
@click.option("--output", default="./output.zip")
@click.option("--partition-by-unit", is_flag=True)
@click.option("--dataset-name", multiple=True, default=[])
def click_export_experiment_data(experiment, output, partition_by_unit, dataset_name):
    """
    (leader only) Export tables from db.
    """
    export_experiment_data(experiment, dataset_name, output, partition_by_unit)
