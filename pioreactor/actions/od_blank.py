# -*- coding: utf-8 -*-
import json
from collections import defaultdict
from statistics import mean

import click

from pioreactor.config import config
from pioreactor.utils import pio_jobs_running
from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor import pubsub
from pioreactor.logging import create_logger


def od_blank(od_angle_channel=None, unit=None, experiment=None, N_samples=30):
    logger = create_logger("od_blank")

    logger.debug("Starting OD blank reading")

    if (
        ("stirring" not in pio_jobs_running())
        # but if test mode, ignore
        and not is_testing_env()
    ):
        logger.error("stirring jobs should be running. Run stirring first.")
        raise ValueError("stirring jobs should be running. Run stirring first. ")

    from pioreactor.background_jobs.od_reading import od_reading

    # we sample faster, because we can...
    # TODO: write tests for this
    assert od_angle_channel is not None, "od_angle_channel is not set"
    sampling_rate = 0.75

    # start od_reading
    od_reading(
        od_angle_channel, sampling_rate, unit=unit, experiment=f"{experiment}-blank"
    )

    def yield_from_mqtt():
        while True:
            msg = pubsub.subscribe(
                f"pioreactor/{unit}/{experiment}-blank/od_reading/od_raw_batched"
            )
            print(msg)
            yield json.loads(msg.payload)

    signal = yield_from_mqtt()
    readings = defaultdict(list)

    try:

        for count, batched_reading in enumerate(signal):
            for (sensor, reading) in batched_reading.items():
                readings[sensor].append(reading)

            print(count)
            if count == N_samples:
                break

        means = {}
        for sensor, reading_series in readings.items():
            # measure the mean and publish. The mean will be used to normalize the readings in downstream jobs
            means[sensor] = mean(reading_series)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_blank/mean",
            json.dumps(means),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )

        logger.debug("OD blank finished")

        return
    except Exception as e:
        logger.error(f"{str(e)}")
        raise e


@click.command(name="od_blank")
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
def click_od_blank(od_angle_channel):
    """
    Compute statistics about the blank OD timeseries
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    od_blank(od_angle_channel, unit, experiment)
