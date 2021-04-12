# -*- coding: utf-8 -*-
import json, time, logging
from collections import defaultdict
from statistics import mean, variance

import click

from pioreactor.config import config
from pioreactor.utils import pio_jobs_running
from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor import pubsub

logger = logging.getLogger("od_normalization")


def od_normalization(od_angle_channel=None, unit=None, experiment=None, N_samples=20):

    logger.debug("Starting OD normalization")

    if (
        ("stirring" not in pio_jobs_running())
        # but if test mode, ignore
        and not is_testing_env()
    ):
        logger.error("stirring jobs should be running. Run stirring first.")
        raise ValueError("stirring jobs should be running. Run stirring first. ")

    if (
        ("od_reading" not in pio_jobs_running())
        # but if test mode, ignore
        and not is_testing_env()
    ):
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
                msg = pubsub.subscribe(
                    f"pioreactor/{unit}/{experiment}/od_raw_batched", allow_retained=False
                )
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
        means = {}
        for sensor, reading_series in readings.items():
            # measure the variance and publish. The variance will be used in downstream jobs.
            variances[sensor] = variance(reading_series)
            # measure the mean and publish. The mean will be used to normalize the readings in downstream jobs
            means[sensor] = mean(reading_series)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps(variances),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            json.dumps(means),
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
