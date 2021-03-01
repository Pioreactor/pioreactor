# -*- coding: utf-8 -*-
# download experiment data
# See create_tables.sql for all tables

import os
from datetime import datetime
import logging
import click
from pioreactor.config import config

logger = logging.getLogger("download_experiment_data")


def download_experiment_data(experiment, output, tables):
    """
    Set an experiment, else it defaults to the entire table.


    """
    import sqlite3
    import zipfile
    import csv

    logger.info("Starting export of data.")

    time = datetime.now().strftime("%Y%m%d%H%m%S")
    zf = zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED)
    con = sqlite3.connect(config["storage"]["database"])

    for table in tables:
        _filename = f"{experiment}-{table}-{time}.dump.csv".replace(" ", "_")
        path_to_file = os.path.join(os.path.dirname(output), _filename)
        cursor = con.cursor()

        if experiment is None:
            query = """SELECT * from :table"""
            cursor.execute(query, {"table": table})

        else:
            query = """
                SELECT * from :table WHERE experiment=:experiment
            """
            cursor.execute(query, {"table": table, "experiment": experiment})

        with open(path_to_file, "w") as csv_file:
            csv_writer = csv.writer(csv_file, delimiter=",")
            csv_writer.writerow([i[0] for i in cursor.description])
            csv_writer.writerows(cursor)

        zf.write(path_to_file, arcname=_filename)

    con.close()
    zf.close()

    logger.info("Completed export of data.")
    return


@click.command(name="download_experiment_data")
@click.option("--experiment", default=None)
@click.option("--output", default="/home/pi/exports/export.zip")
@click.option("--tables", multiple=True, default=[])
def click_download_experiment_data(experiment, output, tables):
    """
    (leader only) Export tables from db.
    """
    return download_experiment_data(experiment, output, tables)
