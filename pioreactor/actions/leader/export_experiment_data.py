# -*- coding: utf-8 -*-
# export experiment data
# See create_tables.sql for all tables
from __future__ import annotations

import os
import re
from contextlib import closing
from contextlib import ExitStack
from datetime import datetime

import click

from pioreactor.config import config
from pioreactor.logging import create_logger


def is_valid_table_name(table_name: str) -> bool:
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


def generate_timestamp_to_localtimestamp_clause(cursor, table_name: str) -> str:
    columns = get_column_names(cursor, table_name)
    timestamp_columns = filter_to_timestamp_columns(columns)

    if not timestamp_columns:
        return ""

    clause = ",".join([f"datetime({c}, 'localtime') as {c}_localtime" for c in timestamp_columns])

    if clause:
        clause += ","

    return clause


def export_experiment_data(
    experiment: str, output: str, partition_by_unit: bool, tables: list
) -> None:
    """
    Set an experiment, else it defaults to the entire table.

    """
    import sqlite3
    import zipfile
    import csv

    if not output.endswith(".zip"):
        print("output should end with .zip")
        raise click.Abort()

    logger = create_logger("export_experiment_data")
    logger.info(f"Starting export of table{'s' if len(tables) > 1 else ''}: {', '.join(tables)}.")

    time = datetime.now().strftime("%Y%m%d%H%M%S")

    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf, closing(
        sqlite3.connect(config["storage"]["database"])
    ) as con:
        for table in tables:
            cursor = con.cursor()

            # so apparently, you can't parameterize the table name in python's sqlite3, so I
            # have to use string formatting (SQL-injection vector), but first check that the table exists (else fail)
            if not (source_exists(cursor, table) and is_valid_table_name(table)):
                raise ValueError(f"Table {table} does not exist.")

            timestamp_to_localtimestamp_clause = generate_timestamp_to_localtimestamp_clause(
                cursor, table
            )

            timestamp_columns = filter_to_timestamp_columns(get_column_names(cursor, table))
            if not timestamp_columns:
                order_by = (
                    "rowid"  # yes this is stupid, but I need a placeholder for the queries below
                )
            else:
                order_by = timestamp_columns[0]  # just take first...

            _partition_by_unit = partition_by_unit
            if table in ("pioreactor_unit_activity_data", "pioreactor_unit_activity_data_rollup"):
                _partition_by_unit = True

            if not _partition_by_unit:
                if experiment is None:
                    query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} ORDER BY {order_by}"
                    cursor.execute(query)
                    filename = f"{table}-{time}.csv"

                else:
                    query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} WHERE experiment=:experiment ORDER BY {order_by}"
                    cursor.execute(query, {"experiment": experiment})
                    filename = f"{experiment}-{table}-{time}.csv"

                filename = filename.replace(" ", "_")
                path_to_file = os.path.join(os.path.dirname(output), filename)
                with open(path_to_file, "w") as csv_file:
                    csv_writer = csv.writer(csv_file, delimiter=",")
                    csv_writer.writerow([_[0] for _ in cursor.description])
                    csv_writer.writerows(cursor)

                zf.write(path_to_file, arcname=filename)
                os.remove(path_to_file)

            else:
                if experiment is None:
                    raise ValueError("Experiment name should be provided.")

                query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} WHERE experiment=:experiment ORDER BY :order_by"
                cursor.execute(query, {"experiment": experiment, "order_by": order_by})

                headers = [_[0] for _ in cursor.description]
                iloc_pioreactor_unit = headers.index("pioreactor_unit")
                filenames = []
                unit_to_writer_map = {}

                with ExitStack() as stack:
                    for row in cursor:
                        unit = row[iloc_pioreactor_unit]
                        if unit not in unit_to_writer_map:
                            filename = f"{experiment}-{table}-{unit}-{time}.csv"
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
                    os.remove(path_to_file)

    logger.info("Finished export.")
    return


@click.command(name="export_experiment_data")
@click.option("--experiment", default=None)
@click.option("--output", default="./output.zip")
@click.option("--partition-by-unit", is_flag=True)
@click.option("--tables", multiple=True, default=[])
def click_export_experiment_data(experiment, output, partition_by_unit, tables):
    """
    (leader only) Export tables from db.
    """
    export_experiment_data(experiment, output, partition_by_unit, tables)
