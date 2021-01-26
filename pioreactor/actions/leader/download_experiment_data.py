# -*- coding: utf-8 -*-
# download experiment data
# See create_tables.sql for all tables

import zipfile
import os
from datetime import datetime
import logging
import click
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.config import config

logger = logging.getLogger("download_experiment_data")


def download_experiment_data(experiment, output, tables):
    import pandas as pd
    import sqlite3

    if experiment == "current":
        experiment = get_latest_experiment_name()

    logger.info("Starting export of data.")

    time = datetime.now().strftime("%Y%m%d%H%m%S")
    zf = zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED)
    con = sqlite3.connect(config["storage"]["database"])

    for table in tables:
        df = pd.read_sql_query(
            f"""
            SELECT * from {table} WHERE experiment="{experiment}"
        """,
            con,
        )

        filename = f"{experiment}-{table}-{time}.dump.csv"
        path_to_file = os.path.join(os.path.dirname(output), filename)
        df.to_csv(path_to_file, index=False)
        zf.write(path_to_file, filename)

    zf.close()

    logger.info("Completed export of data.")
    return


@click.command(name="download_experiment_data")
@click.option("--experiment", default="current")
@click.option("--output", default="/home/pi/exports/export.zip")
@click.option("--tables", multiple=True, default=[])
def click_download_experiment_data(experiment, output, tables):
    """
    (leader only) Export tables from db.
    """
    return download_experiment_data(experiment, output, tables)
