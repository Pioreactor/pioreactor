# -*- coding: utf-8 -*-
"""
TODO: how do I handle a gain that is too small? Ex: an OD is 0.9, but the OD reading starts at max 0.512.

"""
import time
import json
from collections import defaultdict
from statistics import median, variance
import click
import threading
from click import echo, style

from pioreactor.config import config
from pioreactor.utils import pio_jobs_running
from pioreactor.whoami import get_unit_from_hostname, get_latest_experiment_name
from pioreactor import pubsub
from pioreactor.background_jobs.od_reading import od_reading

unit = get_unit_from_hostname()
experiment = get_latest_experiment_name()


def green(msg):
    return style(msg, fg="green")


def bold(msg):
    return style(msg, bold=True)


def od_normalization(od_angle_channel, verbose):
    if "stirring" not in pio_jobs_running():
        raise ValueError("stirring jobs should be running. Run `mb stirring -b` first. ")

    if "od_reading" not in pio_jobs_running():
        # we sample faster, because we can...
        sampling_rate = 0.5
        signal = od_reading(od_angle_channel, verbose, sampling_rate)
    else:
        # not tested
        def yield_from_mqtt():
            while True:
                msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/od_raw_batched")
                yield json.loads(msg.payload)

        signal = yield_from_mqtt()

    echo()
    echo(bold(f"This task will compute statistics from {unit}."))

    time.sleep(0.5)
    readings = defaultdict(list)
    N_samples = 35

    try:

        with click.progressbar(length=N_samples) as bar:
            for count, batched_reading in enumerate(signal):
                for (sensor, reading) in batched_reading.items():
                    readings[sensor].append(reading)

                bar.update(1)
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
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps(variances),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            verbose=verbose,
            retain=True,
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/median",
            json.dumps(medians),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            verbose=verbose,
            retain=True,
        )
        echo(bold("Gathering of statistics complete. They are stored in the message broker."))
        return
    except:
        pass


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
    "--verbose", "-v", count=True, help="print to std. out (may be redirected to pioreactor.log). Increasing values log more."
)
def click_od_normalization(od_angle_channel, verbose):
    od_normalization(od_angle_channel, verbose)


if __name__ == "__main__":
    click_od_normalization()
