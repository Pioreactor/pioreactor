# -*- coding: utf-8 -*-
# download experiment data
# See create_tables.sql for all tables

import zipfile
import os
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.config import config
from pioreactor.pubsub import publish
from pioreactor import whoami
from datetime import datetime
import click


def download_experiment_data(experiment, output, tables):
    import pandas as pd
    import sqlite3

    if not whoami.am_I_leader():
        print(
            f"This command should be run on the {config.leader_hostname} node, not worker."
        )
        return

    publish(
        f"pioreactor/{whoami.unit}/{whoami.experiment}/log",
        f"Starting export of experiment data to {output}.",
        verbose=1,
    )

    if experiment == "current":
        experiment = get_latest_experiment_name()

    time = datetime.now().strftime("%Y%m%d%H%m%S")
    zf = zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED)
    con = sqlite3.connect(config["storage"]["observation_database"])

    for table in tables:
        df = pd.read_sql_query(
            f"""
            SELECT * from {table} WHERE experiment="{experiment}"
        """,
            con,
        )

        filename = f"{experiment}-{table}-{time}.dump.csv.gz"
        path_to_file = os.path.join(os.path.dirname(output), filename)
        df.to_csv(path_to_file, compression="gzip", index=False)
        zf.write(path_to_file, filename)

    zf.close()

    publish(
        f"pioreactor/{whoami.unit}/{whoami.experiment}/log",
        f"Completed export of experiment data to {output}.",
        verbose=1,
    )
    return


@click.command()
@click.option("--experiment", default="current")
@click.option("--output", default="/home/pi/exports/export.zip")
@click.option("--tables", multiple=True, default=[])
def click_download_experiment_data(experiment, output, tables):
    return download_experiment_data(experiment, output, tables)


if __name__ == "__main__":
    click_download_experiment_data()
