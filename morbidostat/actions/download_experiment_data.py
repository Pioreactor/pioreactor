# -*- coding: utf-8 -*-
# download experiment data

from morbidostat.whoami import get_latest_experiment_name
from morbidostat.config import config
from morbidostat.pubsub import publish
from morbidostat import whoami
import click


def download_experiment_data(experiment, output):
    import pandas as pd
    import sqlite3

    if not whoami.am_I_leader():
        print("This command must be run on leader node, not worker.")
        return

    if experiment == "current":
        experiment = get_latest_experiment_name()

    publish(f"morbidostat/{whoami.unit}/{whoami.experiment}/log", f"Starting export of experiment data to {output}.", verbose=1)

    con = sqlite3.connect(config["data"]["observation_database"])

    tables = ["od_readings_raw", "od_readings_filtered", "io_events", "logs", "pid_logs", "growth_rates"]

    for table in tables:
        df = pd.read_sql_query(
            f"""
            SELECT * from {table} WHERE experiment="{experiment}"
        """,
            con,
        )

        df.to_csv(f"{output}/export_{table}.csv.dump.gz", compression="gzip", index=False)

    publish(f"morbidostat/{whoami.unit}/{whoami.experiment}/log", f"Completed export of experiment data to {output}.", verbose=1)
    return


@click.command()
@click.option("--experiment", default="current")
@click.option("--output", default="/home/pi/exports/")
def click_download_experiment_data(experiment, output):
    return download_experiment_data(experiment, output)


if __name__ == "__main__":
    click_download_experiment_data()
