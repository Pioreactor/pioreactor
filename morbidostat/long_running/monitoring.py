"""
Continuously monitor the mordibodstat and take action. This is the core of the io algorithm
"""
import configparser
import time
import threading
import sqlite3

import numpy as np
from scipy.optimize import curve_fit
import pandas as pd

import click
import board
import busio

from morbidostat.actions.take_od_reading import take_od_reading
from morbidostat.actions.add_media import add_media
from morbidostat.actions.remove_waste import remove_waste
from morbidostat.utils.timing_and_threading import every
from paho.mqtt import publish


config = configparser.ConfigParser()
config.read("config.ini")


@click.command()
@click.argument("target_od", type=float)
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--duration", default=10, help="Time, in minutes, between every monitor check")
def monitoring(target_od, unit, duration):
    publish.single(
        f"morbidostat/{unit}/log", f"starting monitoring.py with {duration}min intervals, target OD {target_od}"
    )

    def get_recent_observations():
        # subtract 1 minute because things are a bit wacky post-dilution.
        SQL = f"""
        SELECT
            strftime('%Y-%m-%d %H:%M:%f', 'now', '-{duration-1} minute') as start_time,
            strftime('%Y-%m-%d %H:%M:%f', timestamp) as timestamp,
            od_reading_v
        FROM od_readings_raw
        WHERE datetime(timestamp) > datetime('now','-{duration-1} minute')
        """
        db_location = config["data"]["observation_database"]
        conn = sqlite3.connect(db_location)
        df = pd.read_sql_query(SQL, conn)
        conn.close()

        assert not df.empty, f"Not data retrieved. Check database as {db_location}.\n {SQL}"

        df["x"] = (pd.to_datetime(df["timestamp"]) - pd.to_datetime(df["start_time"])) / np.timedelta64(1, "s")
        return df[["x", "od_reading_v"]]

    def calculate_growth_rate(callback=None):
        def exponential(x, k, A):
            return A * np.exp(k * x)

        df = get_recent_observations()

        x = df["x"].values
        y = df["od_reading_v"].values

        try:
            (rate, A), _ = curve_fit(exponential, x, y, [1 / x.mean(), y.mean()])
        except Exception as e:
            publish.single(f"morbidostat/{unit}/error_log", f"Monitor failed: {str(e)}")
            return

        latest_od = df["od_reading_v"].values[-1]

        publish.single(f"morbidostat/{unit}/log", "Monitor: estimated rate %.2E" % rate)
        publish.single(f"morbidostat/{unit}/log", "Monitor: latest OD %.3f" % latest_od)

        if callback:
            callback(latest_od, rate)
        return

    def turbidostat(latest_od, rate, **args):
        """
        turbidostat mode - try to keep cell density constant
        """
        if latest_od > target_od and rate > 1e-6:
            publish.single(f"morbidostat/{unit}/log", "Monitor triggered IO event.")
            volume = 0.5
            remove_waste(volume, unit)
            time.sleep(0.1)
            add_media(volume, unit)
        return

    # main loop
    try:
        every(duration * 60, calculate_growth_rate, callback=turbidostat)
    except Exception as e:
        publish.single(f"morbidostat/{unit}/error_log", f"Monitor failed: {str(e)}")


if __name__ == "__main__":
    monitoring()
