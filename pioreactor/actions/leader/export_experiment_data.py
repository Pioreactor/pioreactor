# -*- coding: utf-8 -*-
# export experiment data
# See create_tables.sql for all tables

import os
from datetime import datetime

import click
from pioreactor.config import config
from pioreactor.logging import create_logger


def exists_table(cursor, table_name_to_check):
    query = "SELECT 1 FROM sqlite_master WHERE type='table' and name = ?"
    return cursor.execute(query, (table_name_to_check,)).fetchone() is not None


def get_column_names(cursor, table_name):
    query = "PRAGMA table_info(%s)" % table_name
    return [row[1] for row in cursor.execute(query).fetchall()]


def filter_to_timestamp_columns(column_names):
    # We use a standard here: `timestamp` or ends in `_at`
    return [c for c in column_names if (c == "timestamp") or c.endswith("_at")]


def generate_timestamp_to_localtimestamp_clause(cursor, table_name):
    columns = get_column_names(cursor, table_name)
    timestamp_columns = filter_to_timestamp_columns(columns)
    clause = ",".join(
        [f"datetime({c}, 'localtime') as {c}_localtime" for c in timestamp_columns]
    )
    if clause:
        clause += ","
    else:
        return ""


def export_experiment_data(experiment, output, tables):
    """
    Set an experiment, else it defaults to the entire table.

    """
    import sqlite3
    import zipfile
    import csv

    logger = create_logger("export_experiment_data")
    logger.info(f"Starting export of table(s) {tables}.")

    time = datetime.now().strftime("%Y%m%d%H%m%S")
    zf = zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED)
    con = sqlite3.connect(config["storage"]["database"])

    for table in tables:
        cursor = con.cursor()

        # so apparently, you can't parameterise the table name in python's sqlite3, so I
        # have to use string formatting (SQL-injection vector), but first check that the table exists (else fail)
        if not exists_table(cursor, table):
            raise ValueError("table %s does not exist." % table)

        timestamp_to_localtimestamp_clause = generate_timestamp_to_localtimestamp_clause(
            cursor, table
        )

        if experiment is None:
            query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table}"
            cursor.execute(query)
            _filename = f"{table}-{time}.dump.csv".replace(" ", "_")

        else:
            query = f"SELECT {timestamp_to_localtimestamp_clause} * from {table} WHERE experiment=:experiment"
            print(query)
            cursor.execute(query, {"experiment": experiment})
            _filename = f"{experiment}-{table}-{time}.dump.csv".replace(" ", "_")

        path_to_file = os.path.join(os.path.dirname(output), _filename)
        with open(path_to_file, "w") as csv_file:
            csv_writer = csv.writer(csv_file, delimiter=",")
            csv_writer.writerow([i[0] for i in cursor.description])
            csv_writer.writerows(cursor)

        zf.write(path_to_file, arcname=_filename)

    con.close()
    zf.close()

    logger.info("Completed export.")
    return


@click.command(name="export_experiment_data")
@click.option("--experiment", default=None)
@click.option("--output", default="/home/pi/exports/export.zip")
@click.option("--tables", multiple=True, default=[])
def click_export_experiment_data(experiment, output, tables):
    """
    (leader only) Export tables from db.
    """
    return export_experiment_data(experiment, output, tables)
