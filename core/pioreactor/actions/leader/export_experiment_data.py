# -*- coding: utf-8 -*-
# export experiment data
# See create_tables.sql for all tables
import csv
import io
import sqlite3
import sys
import zipfile
from base64 import b64decode
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Sequence

import click
from msgspec import DecodeError
from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.structs import Dataset
from pioreactor.whoami import is_testing_env


def rounded_row_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> tuple[Any, ...]:
    """
    For each value in row, if it's a Python float, round it to N decimals.
    Otherwise, leave it alone.
    Returns a tuple (you could also return a namedtuple or dict if you prefer).
    """
    rounded = []
    for value in row:
        if isinstance(value, float):
            # round(..., N) returns a float with N decimals
            rounded.append(round(value, 12))
        else:
            rounded.append(value)
    return tuple(rounded)


def source_exists(cursor: sqlite3.Cursor, table_name_to_check: str) -> bool:
    query = "SELECT 1 FROM sqlite_master WHERE (type='table' or type='view') and name = ?"
    return cursor.execute(query, (table_name_to_check,)).fetchone() is not None


def generate_timestamp_to_localtimestamp_clause(timestamp_columns: list[str]) -> str:
    if not timestamp_columns:
        return ""

    clause = ",".join(
        [f"strftime('%Y-%m-%d %H:%M:%f', T.{c}, 'localtime') as {c}_localtime" for c in timestamp_columns]
    )

    return clause


def generate_timestamp_to_relative_time_clause(default_order_by: str) -> str:
    if not default_order_by:
        return ""

    START_TIME = "created_at"

    clause = f"(unixepoch(T.{default_order_by}) - unixepoch(E.{START_TIME}))/3600.0 as hours_since_experiment_created"

    return clause


def load_exportable_datasets() -> dict[str, Dataset]:
    if is_testing_env():
        builtins = sorted(Path(".pioreactor/exportable_datasets").glob("*.y*ml"))
        plugins = sorted(Path(".pioreactor/plugins/exportable_datasets").glob("*.y*ml"))
    else:
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


def add_directory_to_zip_with_current_timestamp(zf: zipfile.ZipFile, dir_name: str) -> None:
    """
    Create a directory entry in the zip archive with a sane timestamp.

    Notes
    - zipfile.ZipFile.mkdir() creates a directory entry but leaves the
      date_time at the ZIP format's epoch (1980-01-01) when no timestamp
      is provided, which shows up in some tools as Jan 1, 1980.
    - We explicitly construct a ZipInfo for the directory and set the
      date_time to now so folder metadata looks reasonable.
    """
    # Ensure trailing slash to mark entry as a directory in ZIP
    name = dir_name if dir_name.endswith("/") else f"{dir_name}/"

    info = zipfile.ZipInfo(name)
    # Current local time within ZIP's supported range
    info.date_time = datetime.now().timetuple()[:6]
    # Set POSIX permissions (rwxr-xr-x). Many tools infer directory from the trailing slash.
    info.external_attr = 0o755 << 16

    # Write an empty payload for the directory entry
    zf.writestr(info, b"")


def cleanup_stale_export_artifacts(exports_dir: Path, logger: Any | None = None) -> None:
    """
    Remove incomplete export artifacts left behind by interrupted UI exports.
    """
    if not exports_dir.exists():
        return

    for pattern in ("*.tmp", "*.csv"):
        for artifact in exports_dir.glob(pattern):
            if not artifact.is_file():
                continue
            try:
                artifact.unlink()
            except OSError as exc:
                if logger is not None:
                    logger.debug(f"Unable to remove stale export artifact {artifact}: {exc}")


def validate_dataset_information(dataset: Dataset, cursor: sqlite3.Cursor) -> None:
    if not (dataset.table or dataset.query):
        raise ValueError("query or table must be defined.")

    if dataset.table:
        table = dataset.table
        if not source_exists(cursor, table):
            raise ValueError(f"Table {table} does not exist.")


def create_experiment_clause(
    experiments: Sequence[str], existing_placeholders: dict[str, str]
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
    local_timetamp_clause = f"strftime('%Y-%m-%dT%H:%M:%f', T.{time_column}, 'localtime')"
    if start_time is not None and end_time is not None:
        existing_placeholders["start_time"] = start_time
        existing_placeholders["end_time"] = end_time
        return (
            f"{local_timetamp_clause} >= :start_time AND {local_timetamp_clause} <= :end_time",
            existing_placeholders,
        )

    elif start_time is not None:
        existing_placeholders["start_time"] = start_time
        return f"{local_timetamp_clause} >= :start_time", existing_placeholders

    elif end_time is not None:
        existing_placeholders["end_time"] = end_time
        return f"{local_timetamp_clause} <= :end_time", existing_placeholders
    else:
        raise ValueError


def create_sql_query(
    selects: list[str],
    table_or_subquery: str,
    existing_placeholders: dict[str, str],
    where_clauses: list[str] | None = None,
    order_by_col: str | None = None,
    order_by_cols: Sequence[str] | None = None,
    has_experiment: bool = False,
) -> tuple[str, dict[str, str]]:
    """
    Constructs an SQL query with SELECT, FROM, WHERE, and ORDER BY clauses.
    """
    # Base SELECT and FROM clause
    query = f"SELECT {', '.join(selects)} FROM ({table_or_subquery}) T"

    if has_experiment:
        query += " LEFT JOIN experiments E ON E.experiment = T.experiment"  # left join since some experiments, like $experiment, are virtual. Maybe this shouldn't be the case?

    # Add WHERE clause if provided
    if where_clauses:
        query += f" WHERE {' AND '.join(where_clauses)}"

    if order_by_cols:
        query += f" ORDER BY {', '.join(f'T.{column}' for column in order_by_cols)}"
    elif order_by_col:
        query += f" ORDER BY T.{order_by_col}"

    return query, existing_placeholders


def export_experiment_data(
    experiments: Sequence[str],
    dataset_names: Sequence[str],
    output: str,
    start_time: str | None = None,
    end_time: str | None = None,
    partition_by_unit: bool = False,
    partition_by_experiment: bool = True,
) -> None:
    """
    Set an experiment, else it defaults to the entire table.
    """
    if not output.endswith(".zip"):
        click.echo("output should end with .zip")
        sys.exit(1)

    if len(dataset_names) == 0:
        click.echo("At least one dataset name must be provided.")
        sys.exit(1)

    logger = create_logger("export_experiment_data", experiment="$experiment")
    logger.info(
        f"Starting export of dataset{'s' if len(dataset_names) > 1 else ''}: {', '.join(dataset_names)} to {output}."
    )

    time = datetime.now().strftime("%Y%m%d%H%M%S")

    available_datasets = load_exportable_datasets()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_output_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_output_path.unlink(missing_ok=True)

    try:
        with zipfile.ZipFile(tmp_output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf, closing(
            sqlite3.connect(f"file:{config.get('storage', 'database')}?mode=ro", uri=True)
        ) as con:
            con.create_function(
                "BASE64", 1, decode_base64
            )  # TODO: until next OS release which implements a native sqlite3 base64 function

            con.row_factory = rounded_row_factory

            cursor = con.cursor()
            cursor.executescript(
                """
                PRAGMA busy_timeout = 15000;
                PRAGMA synchronous = 1; -- aka NORMAL, recommended when using WAL
                PRAGMA temp_store = 1;  -- large export sorts should spill to disk, not RAM
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

                _partition_by_unit = dataset.has_unit and (
                    partition_by_unit or dataset.always_partition_by_unit
                )
                _partition_by_experiment = dataset.has_experiment and partition_by_experiment
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
                    selects,
                    table_or_subquery,
                    placeholders,
                    where_clauses,
                    order_by_col=None,
                    has_experiment=dataset.has_experiment,
                )
                cursor.execute(query, placeholders)

                headers = [_[0] for _ in cursor.description]

                order_by_cols: list[str] = []
                if _partition_by_experiment:
                    try:
                        iloc_experiment = headers.index("experiment")
                        order_by_cols.append("experiment")
                    except ValueError:
                        iloc_experiment = None
                else:
                    iloc_experiment = None

                if _partition_by_unit:
                    try:
                        iloc_unit = headers.index("pioreactor_unit")
                        order_by_cols.append("pioreactor_unit")
                    except ValueError:
                        iloc_unit = None
                else:
                    iloc_unit = None

                if order_by_col and order_by_col not in order_by_cols:
                    order_by_cols.append(order_by_col)

                query, placeholders = create_sql_query(
                    selects,
                    table_or_subquery,
                    placeholders,
                    where_clauses,
                    order_by_cols=order_by_cols,
                    has_experiment=dataset.has_experiment,
                )
                cursor.execute(query, placeholders)

                count = 0
                current_partition: tuple[Any, Any] | None = None
                current_csv_file: Any | None = None
                current_csv_writer: Any | None = None

                add_directory_to_zip_with_current_timestamp(zf, dataset_name)

                try:
                    for row in cursor:
                        count += 1
                        rows_partition = (
                            row[iloc_experiment] if iloc_experiment is not None else "all_experiments",
                            row[iloc_unit] if iloc_unit is not None else "all_units",
                        )

                        if rows_partition != current_partition:
                            if current_csv_file is not None:
                                current_csv_file.close()

                            filename = (
                                f"{dataset_name}-"
                                + "-".join(str(partition) for partition in rows_partition)
                                + f"-{time}.csv"
                            )
                            filename = filename.replace(" ", "_")
                            zip_member = f"{dataset_name}/{filename}"
                            current_csv_file = io.TextIOWrapper(
                                zf.open(zip_member, mode="w"),
                                encoding="utf-8",
                                newline="",
                            )
                            current_csv_writer = csv.writer(current_csv_file, delimiter=",")
                            current_csv_writer.writerow(headers)
                            current_partition = rows_partition

                        assert current_csv_writer is not None
                        current_csv_writer.writerow(row)

                        if count % 10_000 == 0:
                            logger.debug(f"Exported {count} rows...")
                finally:
                    if current_csv_file is not None:
                        current_csv_file.close()

                logger.debug(f"Exported {count} rows from {dataset_name}.")
                if count == 0:
                    logger.warning(f"No data present in {dataset_name} with applied filters.")

        tmp_output_path.replace(output_path)
        logger.info(f"Finished export to {output}.")
    except Exception:
        tmp_output_path.unlink(missing_ok=True)
        raise

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
    experiment: tuple[str, ...],
    output: str,
    partition_by_unit: bool,
    partition_by_experiment: bool,
    dataset_name: tuple[str, ...],
    start_time: str | None,
    end_time: str | None,
) -> None:
    """
    (leader only) Export datasets from db.
    """
    export_experiment_data(
        experiment, dataset_name, output, start_time, end_time, partition_by_unit, partition_by_experiment
    )
