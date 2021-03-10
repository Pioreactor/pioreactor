# -*- coding: utf-8 -*-
import time
import json
from collections import defaultdict
from statistics import median, variance
import logging

import click

from pioreactor.config import config
from pioreactor.utils import pio_jobs_running
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor import pubsub

logger = logging.getLogger("od_normalization")


def od_normalization(od_angle_channel=None, unit=None, experiment=None, N_samples=25):

    logger.debug("Starting OD normalization")

    if "stirring" not in pio_jobs_running():
        logger.error("stirring jobs should be running. Run `mb stirring -b` first.")
        raise ValueError("stirring jobs should be running. Run `mb stirring -b` first. ")

    if "od_reading" not in pio_jobs_running():
        from pioreactor.background_jobs.od_reading import od_reading

        # we sample faster, because we can...
        # TODO: write tests for this
        assert od_angle_channel is not None, "od_angle_channel is not set"
        sampling_rate = 0.5
        signal = od_reading(od_angle_channel, sampling_rate)
    else:
        # TODO: write tests for this
        def yield_from_mqtt():
            while True:
                msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/od_raw_batched")
                yield json.loads(msg.payload)

        signal = yield_from_mqtt()

    time.sleep(0.5)
    readings = defaultdict(list)

    try:

        for count, batched_reading in enumerate(signal):
            for (sensor, reading) in batched_reading.items():
                readings[sensor].append(reading)

            if count == N_samples:
                break

        variances = {}
        medians = {}
        for sensor, reading_series in readings.items():
            # measure the variance and publish. The variance will be used in downstream jobs.
            variances[sensor] = variance(reading_series)
            # measure the median and publish. The median will be used to normalize the readings in downstream jobs
            medians[sensor] = median(reading_series)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps(variances),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/median",
            json.dumps(medians),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )

        logger.debug("OD normalization finished")

        return
    except Exception as e:
        logger.error(f"{str(e)}")
        raise e


@click.command(name="od_normalization")
@click.option(
    "--od-angle-channel",
    multiple=True,
    default=list(config["od_config.photodiode_channel"].values()),
    type=click.STRING,
    help="""
pair of angle,channel for optical density reading. Can be invoked multiple times. Ex:

--od-angle-channel 135,0 --od-angle-channel 90,1 --od-angle-channel 45,2

""",
)
def click_od_normalization(od_angle_channel):
    """
    Compute statistics about the OD timeseries
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    od_normalization(od_angle_channel, unit, experiment)
