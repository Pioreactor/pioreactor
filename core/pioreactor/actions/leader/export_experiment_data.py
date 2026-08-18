# -*- coding: utf-8 -*-
# export experiment data
# See create_tables.sql for all tables
import csv
import io
import json
import os
import shutil
import sqlite3
import sys
import zipfile
from base64 import b64decode
from contextlib import closing
from datetime import datetime
from datetime import timezone
from pathlib import Path
from time import monotonic
from typing import Any
from typing import Sequence

import click
from msgspec import DecodeError
from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.structs import Dataset
from pioreactor.utils.timing import to_iso_format
from pioreactor.version import __version__
from pioreactor.whoami import is_testing_env


MINIMUM_EXPORT_FREE_BYTES = 64 * 1024 * 1024
MINIMUM_EXPORT_AVAILABLE_MEMORY_BYTES = 120 * 1024 * 1024
MAX_EXPORT_WAL_BYTES = 512 * 1024 * 1024
EXPORT_RESOURCE_CHECK_INTERVAL_ROWS = 5_000
EXPORT_RESOURCE_CHECK_INTERVAL_SECONDS = 2.0
EXPORT_METADATA_SCHEMA_VERSION = 1


class ExportResourceLimitError(RuntimeError):
    pass


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


def write_json_to_zip_with_current_timestamp(zf: zipfile.ZipFile, name: str, data: dict[str, Any]) -> None:
    info = zipfile.ZipInfo(name)
    info.date_time = datetime.now().timetuple()[:6]
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))


def build_dataset_schema(dataset: Dataset, headers: Sequence[str]) -> dict[str, Any]:
    timestamp_localtime_columns = [f"{column}_localtime" for column in dataset.timestamp_columns]
    generated_columns = [
        column
        for column in [*timestamp_localtime_columns, "hours_since_experiment_created"]
        if column in headers
    ]
    entity_columns = [
        column
        for column in ("experiment", "pioreactor_unit")
        if column in headers
        and (
            (column == "experiment" and dataset.has_experiment)
            or (column == "pioreactor_unit" and dataset.has_unit)
        )
    ]

    columns: list[dict[str, Any]] = []
    for column in headers:
        column_schema: dict[str, Any] = {
            "name": column,
            "generated": column in generated_columns,
        }
        if description := dataset.column_descriptions.get(column):
            column_schema["description"] = description
        if unit := dataset.column_units.get(column):
            column_schema["unit"] = unit
        columns.append(column_schema)

    return {
        "schema_version": EXPORT_METADATA_SCHEMA_VERSION,
        "dataset_name": dataset.dataset_name,
        "display_name": dataset.display_name,
        "description": dataset.description,
        "source": dataset.source,
        "table": dataset.table,
        "query": dataset.query,
        "default_order_by": dataset.default_order_by,
        "timestamp_columns": dataset.timestamp_columns,
        "entity_columns": entity_columns,
        "generated_columns": generated_columns,
        "columns": columns,
    }


def build_export_manifest(
    *,
    export_created_at: str,
    experiment: str,
    selected_datasets: Sequence[str],
    start_time: str | None,
    end_time: str | None,
    partition_by_unit: bool,
    partition_by_experiment: bool,
    datasets: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": EXPORT_METADATA_SCHEMA_VERSION,
        "pioreactor_version": __version__,
        "export_created_at": export_created_at,
        "filters": {
            "experiment": experiment,
            "start_time": start_time,
            "end_time": end_time,
            "partition_by_unit": partition_by_unit,
            "partition_by_experiment": partition_by_experiment,
        },
        "selected_datasets": list(selected_datasets),
        "datasets": datasets,
    }


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


def _read_mem_available_bytes(meminfo_path: Path = Path("/proc/meminfo")) -> int | None:
    if not meminfo_path.exists():
        return None

    for line in meminfo_path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key != "MemAvailable":
            continue
        amount, unit, *_ = value.strip().split()
        if unit != "kB":
            return None
        return int(amount) * 1024

    return None


def _get_sqlite_temp_directory() -> Path:
    # Keep this in SQLite's Unix temp-directory search order. We intentionally
    # do not mutate SQLite's deprecated process-global temp directory at runtime.
    candidates = (
        os.environ.get("SQLITE_TMPDIR"),
        os.environ.get("TMPDIR"),
        "/var/tmp",
        "/usr/tmp",
        "/tmp",
        ".",
    )

    for candidate in candidates:
        if not candidate:
            continue

        path = Path(candidate)
        if path.is_dir() and os.access(path, os.W_OK | os.X_OK):
            return path

    raise ExportResourceLimitError("Export cannot find a writable directory for SQLite temporary files.")


def _check_export_resources(output_path: Path, database_path: Path) -> None:
    mem_available_bytes = _read_mem_available_bytes()
    if mem_available_bytes is not None and mem_available_bytes < MINIMUM_EXPORT_AVAILABLE_MEMORY_BYTES:
        available_mb = mem_available_bytes // (1024 * 1024)
        required_mb = MINIMUM_EXPORT_AVAILABLE_MEMORY_BYTES // (1024 * 1024)
        raise ExportResourceLimitError(
            f"Export stopped because available memory is low. {required_mb} MB required, {available_mb} MB available."
        )

    for path in [output_path.parent, _get_sqlite_temp_directory()]:
        free_bytes = shutil.disk_usage(path).free
        if free_bytes < MINIMUM_EXPORT_FREE_BYTES:
            free_mb = free_bytes // (1024 * 1024)
            required_mb = MINIMUM_EXPORT_FREE_BYTES // (1024 * 1024)
            raise ExportResourceLimitError(
                f"Export stopped because {path} is low on free space. {required_mb} MB required, {free_mb} MB available."
            )

    wal_path = Path(f"{database_path}-wal")
    if wal_path.exists():
        wal_size_bytes = wal_path.stat().st_size
        if wal_size_bytes > MAX_EXPORT_WAL_BYTES:
            wal_size_mb = wal_size_bytes // (1024 * 1024)
            max_wal_mb = MAX_EXPORT_WAL_BYTES // (1024 * 1024)
            raise ExportResourceLimitError(
                f"Export stopped because SQLite WAL grew too large. {max_wal_mb} MB limit, {wal_size_mb} MB current."
            )


def validate_dataset_information(dataset: Dataset, cursor: sqlite3.Cursor) -> None:
    if not (dataset.table or dataset.query):
        raise ValueError("query or table must be defined.")

    if dataset.table:
        table = dataset.table
        if not source_exists(cursor, table):
            raise ValueError(f"Table {table} does not exist.")


def create_timespan_clause(
    start_time: str | None, end_time: str | None, time_column: str, existing_placeholders: dict[str, str]
) -> tuple[str, dict[str, str]]:
    if start_time is not None and end_time is not None:
        existing_placeholders["start_time"] = start_time
        existing_placeholders["end_time"] = end_time
        return (
            f"T.{time_column} >= :start_time AND T.{time_column} <= :end_time",
            existing_placeholders,
        )

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
    experiment: str,
    dataset_names: Sequence[str],
    output: str,
    start_time: str | None = None,
    end_time: str | None = None,
    partition_by_unit: bool = False,
    partition_by_experiment: bool = True,
) -> None:
    """
    Export datasets for exactly one experiment.
    """
    if not isinstance(experiment, str) or not experiment:
        raise ValueError("Exactly one experiment must be provided.")

    if not output.endswith(".zip"):
        click.echo("output should end with .zip")
        sys.exit(1)

    if len(dataset_names) == 0:
        click.echo("At least one dataset name must be provided.")
        sys.exit(1)

    start_time_as_datetime = datetime.fromisoformat(start_time) if start_time is not None else None
    end_time_as_datetime = datetime.fromisoformat(end_time) if end_time is not None else None
    if start_time_as_datetime is not None and start_time_as_datetime.tzinfo is None:
        raise ValueError("start_time must include a timezone offset")
    if end_time_as_datetime is not None and end_time_as_datetime.tzinfo is None:
        raise ValueError("end_time must include a timezone offset")
    if (
        start_time_as_datetime is not None
        and end_time_as_datetime is not None
        and start_time_as_datetime > end_time_as_datetime
    ):
        raise ValueError("start_time must be earlier than or equal to end_time")
    start_time = (
        to_iso_format(start_time_as_datetime.astimezone(timezone.utc))
        if start_time_as_datetime is not None
        else None
    )
    end_time = (
        to_iso_format(end_time_as_datetime.astimezone(timezone.utc))
        if end_time_as_datetime is not None
        else None
    )

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
    database_path = Path(config.get("storage", "database"))
    _check_export_resources(tmp_output_path, database_path)
    resource_limit_error: ExportResourceLimitError | None = None
    last_sqlite_progress_resource_check = 0.0
    export_created_at = datetime.now().astimezone().isoformat()
    manifest_datasets: list[dict[str, Any]] = []

    def check_resources_from_sqlite_progress() -> int:
        nonlocal last_sqlite_progress_resource_check
        nonlocal resource_limit_error

        now = monotonic()
        if now - last_sqlite_progress_resource_check < EXPORT_RESOURCE_CHECK_INTERVAL_SECONDS:
            return 0

        try:
            _check_export_resources(tmp_output_path, database_path)
        except ExportResourceLimitError as exc:
            resource_limit_error = exc
            return 1

        last_sqlite_progress_resource_check = now
        return 0

    try:
        with zipfile.ZipFile(tmp_output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf, closing(
            sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        ) as con:
            con.create_function(
                "BASE64", 1, decode_base64
            )  # SQLite bundles base64() with its CLI, but not with the library used by Python.

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
            con.set_progress_handler(check_resources_from_sqlite_progress, 50_000)

            for dataset_name in dataset_names:
                _check_export_resources(tmp_output_path, database_path)

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
                    placeholders["experiment"] = experiment
                    where_clauses.append("T.experiment = :experiment")

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
                cursor.execute(f"SELECT * FROM ({query}) LIMIT 0", placeholders)

                headers = [_[0] for _ in cursor.description]
                schema_path = f"{dataset_name}/schema.json"
                dataset_schema = build_dataset_schema(dataset, headers)

                order_by_cols: list[str] = []
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
                current_csv_manifest_entry: dict[str, Any] | None = None
                csv_manifest_entries: list[dict[str, Any]] = []
                last_resource_check = monotonic()

                add_directory_to_zip_with_current_timestamp(zf, dataset_name)
                write_json_to_zip_with_current_timestamp(zf, schema_path, dataset_schema)

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
                            zip_info = zipfile.ZipInfo(zip_member)
                            zip_info.date_time = datetime.now().timetuple()[:6]
                            zip_info.compress_type = zipfile.ZIP_DEFLATED
                            zip_info.compress_level = 1
                            zip_info.external_attr = 0o644 << 16
                            current_csv_file = io.TextIOWrapper(
                                zf.open(zip_info, mode="w"),
                                encoding="utf-8",
                                newline="",
                            )
                            current_csv_writer = csv.writer(current_csv_file, delimiter=",")
                            current_csv_writer.writerow(headers)
                            current_partition = rows_partition
                            current_csv_manifest_entry = {
                                "path": zip_member,
                                "row_count": 0,
                                "partition": {
                                    "experiment": rows_partition[0],
                                    "pioreactor_unit": rows_partition[1],
                                },
                            }
                            csv_manifest_entries.append(current_csv_manifest_entry)

                        assert current_csv_writer is not None
                        assert current_csv_manifest_entry is not None
                        current_csv_writer.writerow(row)
                        current_csv_manifest_entry["row_count"] += 1

                        if count % 10_000 == 0:
                            logger.debug(f"Exported {count} rows...")

                        if count % EXPORT_RESOURCE_CHECK_INTERVAL_ROWS == 0:
                            now = monotonic()
                            if now - last_resource_check >= EXPORT_RESOURCE_CHECK_INTERVAL_SECONDS:
                                _check_export_resources(tmp_output_path, database_path)
                                last_resource_check = now
                finally:
                    if current_csv_file is not None:
                        current_csv_file.close()

                logger.debug(f"Exported {count} rows from {dataset_name}.")
                if count == 0:
                    logger.warning(f"No data present in {dataset_name} with applied filters.")

                partition_experiments = sorted(
                    {
                        entry["partition"]["experiment"]
                        for entry in csv_manifest_entries
                        if entry["partition"]["experiment"] != "all_experiments"
                    }
                )
                partition_units = sorted(
                    {
                        entry["partition"]["pioreactor_unit"]
                        for entry in csv_manifest_entries
                        if entry["partition"]["pioreactor_unit"] != "all_units"
                    }
                )
                manifest_datasets.append(
                    {
                        "dataset_name": dataset_name,
                        "display_name": dataset.display_name,
                        "schema_path": schema_path,
                        "csv_paths": [entry["path"] for entry in csv_manifest_entries],
                        "csv_files": csv_manifest_entries,
                        "row_count": count,
                        "partition_values": {
                            "experiments": partition_experiments,
                            "pioreactor_units": partition_units,
                        },
                    }
                )

            write_json_to_zip_with_current_timestamp(
                zf,
                "manifest.json",
                build_export_manifest(
                    export_created_at=export_created_at,
                    experiment=experiment,
                    selected_datasets=dataset_names,
                    start_time=start_time,
                    end_time=end_time,
                    partition_by_unit=partition_by_unit,
                    partition_by_experiment=partition_by_experiment,
                    datasets=manifest_datasets,
                ),
            )

        tmp_output_path.replace(output_path)
        logger.info(f"Finished export to {output}.")
    except Exception as exc:
        tmp_output_path.unlink(missing_ok=True)
        if resource_limit_error is not None:
            raise resource_limit_error from exc
        raise

    return


@click.command(name="export_experiment_data")
@click.option("--experiment", required=True)
@click.option("--output", default="./output.zip")
@click.option("--partition-by-unit", is_flag=True)
@click.option("--partition-by-experiment", is_flag=True)
@click.option("--dataset-name", multiple=True, default=[])
@click.option("--start-time", help="Offset-aware ISO-8601 timestamp.")
@click.option("--end-time", help="Offset-aware ISO-8601 timestamp.")
def click_export_experiment_data(
    experiment: str,
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
