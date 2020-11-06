# -*- coding: utf-8 -*-
"""


"""
import time
import json
import os
import string
from collections import defaultdict
from statistics import median, variance
import click
import threading
from click import echo, style

from morbidostat.utils import log_start, log_stop
from morbidostat.whoami import unit, experiment, hostname
from morbidostat.config import config
from morbidostat import pubsub
from morbidostat.utils.timing import every
from morbidostat.background_jobs.od_reading import od_reading
from morbidostat.background_jobs.stirring import stirring


def start_stirring_in_background_thread(verbose):
    thread = threading.Thread(target=stirring, kwargs={"verbose": verbose, "duration": 1000})
    thread.start()
    return thread


def green(msg):
    return style(msg, fg="green")


def bold(msg):
    return style(msg, bold=True)


@log_start(unit, experiment)
@log_stop(unit, experiment)
def od_normalization(od_angle_channel, verbose):
    echo(green(f"This task will compute statistics from the morbidostat unit {hostname}."))

    echo(green("Starting stirring"))
    # stirring_thread = start_stirring_in_background_thread(verbose)

    click.confirm(bold(f"Place vial with media in {hostname}. Is the vial in place?"))

    readings = defaultdict(list)
    sampling_rate = 0.5

    N_samples = 50
    with click.progressbar(length=N_samples) as bar:
        for count, batched_reading in enumerate(od_reading(od_angle_channel, verbose, sampling_rate)):
            for (sensor, reading) in batched_reading.items():
                readings[sensor].append(reading)

            bar.update(count)
            if count == N_samples:
                break

    variances = {}
    medians = {}
    for sensor, reading_series in readings.items():
        # measure the variance and publish. The variance will be used in downstream jobs.
        var = variance(reading_series)
        echo(green(f"variance of {sensor} = {var}"))
        variances[sensor] = var
        # measure the median and publish. The median will be used to normalize the readings in downstream jobs
        med = median(reading_series)
        echo(green(f"median of {sensor} = {med}"))
        medians[sensor] = med

    pubsub.publish(
        f"morbidostat/{unit}/{experiment}/od_normalization/variance", variances, qos=pubsub.AT_LEAST_ONCE, verbose=verbose
    )
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_normalization/median", medians, qos=pubsub.AT_LEAST_ONCE, verbose=verbose)


@click.command()
@click.option(
    "--od-angle-channel",
    multiple=True,
    default=list(config["od_config"].values()),
    type=click.STRING,
    help="""
pair of angle,channel for optical density reading. Can be invoked multiple times. Ex:

--od-angle-channel 135,0 --od-angle-channel 90,1 --od-angle-channel 45,2

""",
)
@click.option(
    "--verbose", "-v", count=True, help="print to std. out (may be redirected to morbidostat.log). Increasing values log more."
)
def click_od_normalization(od_angle_channel, verbose):
    od_normalization(od_angle_channel, verbose)


if __name__ == "__main__":
    click_od_normalization()
