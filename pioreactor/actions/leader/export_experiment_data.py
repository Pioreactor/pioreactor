# -*- coding: utf-8 -*-
# export experiment data
# See create_tables.sql for all tables
from __future__ import annotations

import os
from datetime import datetime

import click

from pioreactor.config import config
from pioreactor.logging import create_logger


def exists_table(cursor, table_name_to_check: str) -> bool:
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
    clause = ",".join(
        [f"datetime({c}, 'localtime') as {c}_localtime" for c in timestamp_columns]
    )
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
    logger.info(
        f"Starting export of table{'s' if len(tables) > 1 else ''}: {', '.join(tables)}."
    )

    time = datetime.now().strftime("%Y%m%d%H%m%S")
    zf = zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED)
    con = sqlite3.connect(config["storage"]["database"])

    for table in tables:
        cursor = con.cursor()

        # so apparently, you can't parameterize the table name in python's sqlite3, so I
        # have to use string formatting (SQL-injection vector), but first check that the table exists (else fail)
        if not exists_table(cursor, table):
            raise ValueError(f"Table {table} does not exist.")

        timestamp_to_localtimestamp_clause = generate_timestamp_to_localtimestamp_clause(
            cursor, table
        )
        order_by = filter_to_timestamp_columns(
            get_column_names(cursor, table)
        ).pop()  # just take first...

        if experiment is None:
            query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} ORDER BY :order_by"
            cursor.execute(query, {"order_by": order_by})
            _filename = f"{table}-{time}.dump.csv".replace(" ", "_")

        else:
            query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} WHERE experiment=:experiment ORDER BY :order_by"
            cursor.execute(query, {"experiment": experiment, "order_by": order_by})
            _filename = f"{experiment}-{table}-{time}.dump.csv".replace(" ", "_")

        path_to_file = os.path.join(os.path.dirname(output), _filename)
        with open(path_to_file, "w") as csv_file:
            csv_writer = csv.writer(csv_file, delimiter=",")
            csv_writer.writerow([i[0] for i in cursor.description])
            csv_writer.writerows(cursor)

        zf.write(path_to_file, arcname=_filename)

    con.close()
    zf.close()

    logger.info("Finished export.")
    return


@click.command(name="export_experiment_data")
@click.option("--experiment", default=None)
@click.option("--output", default="/home/pi/exports/export.zip")
@click.option("--tables", multiple=True, default=[])
def click_export_experiment_data(experiment, output, tables):
    """
    (leader only) Export tables from db.
    """
    export_experiment_data(experiment, output, tables)
