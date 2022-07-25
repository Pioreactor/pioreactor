# -*- coding: utf-8 -*-
# export experiment data
# See create_tables.sql for all tables
from __future__ import annotations

import os
from contextlib import closing
from contextlib import ExitStack
from datetime import datetime

import click

from pioreactor.config import config
from pioreactor.logging import create_logger


def table_exists(cursor, table_name_to_check: str) -> bool:
    query = "SELECT 1 FROM sqlite_master WHERE type='table' and name = ?"
    return cursor.execute(query, (table_name_to_check,)).fetchone() is not None


def get_column_names(cursor, table_name: str) -> list[str]:
    query = f"PRAGMA table_info({table_name})"
    return [row[1] for row in cursor.execute(query).fetchall()]


def filter_to_timestamp_columns(column_names: list[str]) -> list[str]:
    # We use a standard here: `timestamp` or ends in `_at`
    return [c for c in column_names if (c == "timestamp") or c.endswith("_at")]


def generate_timestamp_to_localtimestamp_clause(cursor, table_name: str) -> str:
    # TODO: this assumes a timestamp column exists?
    columns = get_column_names(cursor, table_name)
    timestamp_columns = filter_to_timestamp_columns(columns)
    clause = ",".join([f"datetime({c}, 'localtime') as {c}_localtime" for c in timestamp_columns])
    if clause:
        clause += ","

    return clause


def export_experiment_data(experiment: str, output: str, tables: list) -> None:
    """
    Set an experiment, else it defaults to the entire table.

    """
    import sqlite3
    import zipfile
    import csv

    logger = create_logger("export_experiment_data")
    logger.info(f"Starting export of table{'s' if len(tables) > 1 else ''}: {', '.join(tables)}.")

    time = datetime.now().strftime("%Y%m%d%H%m%S")

    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf, closing(
        sqlite3.connect(config["storage"]["database"])
    ) as con:

        for table in tables:

            cursor = con.cursor()

            # so apparently, you can't parameterize the table name in python's sqlite3, so I
            # have to use string formatting (SQL-injection vector), but first check that the table exists (else fail)
            if not table_exists(cursor, table):
                raise ValueError(f"Table {table} does not exist.")

            timestamp_to_localtimestamp_clause = generate_timestamp_to_localtimestamp_clause(
                cursor, table
            )
            order_by = filter_to_timestamp_columns(
                get_column_names(cursor, table)
            ).pop()  # just take first...

            partition_by_unit = False
            if table == "pioreactor_unit_accumulating_state":
                partition_by_unit = True

            if not partition_by_unit:

                if experiment is None:
                    query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} ORDER BY :order_by"
                    cursor.execute(query, {"order_by": order_by})
                    filename = f"{table}-{time}.csv"

                else:
                    query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} WHERE experiment=:experiment ORDER BY :order_by"
                    cursor.execute(query, {"experiment": experiment, "order_by": order_by})
                    filename = f"{experiment}-{table}-{time}.csv"

                filename = filename.replace(" ", "_")
                path_to_file = os.path.join(os.path.dirname(output), filename)
                with open(path_to_file, "w") as csv_file:
                    csv_writer = csv.writer(csv_file, delimiter=",")
                    csv_writer.writerow([_[0] for _ in cursor.description])
                    csv_writer.writerows(cursor)

                zf.write(path_to_file, arcname=filename)

            else:
                query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} WHERE experiment=:experiment ORDER BY :order_by"
                cursor.execute(query, {"experiment": experiment, "order_by": order_by})

                headers = [_[0] for _ in cursor.description]
                iloc_pioreactor_unit = headers.index("pioreactor_unit")
                filenames = []
                file_map = {}

                with ExitStack() as stack:
                    for row in cursor:
                        unit = row[iloc_pioreactor_unit]
                        if unit not in file_map:
                            filename = f"{experiment}-{table}-{unit}-{time}.csv"
                            filenames.append(filename)
                            file_map[unit] = csv.writer(
                                stack.enter_context(open(filename, "w")), delimiter=","
                            )
                            file_map[unit].writerow(headers)

                        file_map[unit].writerow(row)

                for filename in filenames:
                    path_to_file = os.path.join(os.path.dirname(output), filename)
                    zf.write(path_to_file, arcname=filename)

    logger.info("Finished export.")
    return


@click.command(name="export_experiment_data")
@click.option("--experiment", default=None)
@click.option("--output", default="/home/pioreactor/exports/export.zip")
@click.option("--tables", multiple=True, default=[])
def click_export_experiment_data(experiment, output, tables):
    """
    (leader only) Export tables from db.
    """
    export_experiment_data(experiment, output, tables)
