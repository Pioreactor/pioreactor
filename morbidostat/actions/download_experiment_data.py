# -*- coding: utf-8 -*-
# download experiment data


from morbidostat.utils import config, get_latest_experiment_name
import click


def download_experiment_data(experiment, output):
    import pandas as pd
    import sqlite3

    if experiment == "current":
        experiment = get_latest_experiment_name()

    con = sqlite3.connect(config["data"]["observation_database"])

    tables = ["od_readings_raw", "od_readings_filtered", "io_events", "logs", "pid_logs", "growth_rates"]

    for table in tables:
        print(f"exporting {table}.")
        df = pd.read_sql_query(
            f"""
            SELECT * from {table} WHERE experiment="{experiment}"
        """,
            con,
        )

        df.to_csv(f"{output}/export_{table}.csv.dump.gz", compression="gzip", index=False)

    return


@click.command()
@click.option("--experiment", default="current")
@click.option("--output", default="/home/pi/db")
def click_download_experiment_data(experiment, output):
    return download_experiment_data(experiment, output)


if __name__ == "__main__":
    click_download_experiment_data()
