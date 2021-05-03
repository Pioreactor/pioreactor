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
from pioreactor.background_jobs.od_reading import (
    ODReader,
    create_channel_label_map_from_string,
)


def od_blank(od_angle_channel, unit=None, experiment=None, N_samples=30):
    logger = create_logger("od_blank")

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/od_blank/$state",
        "ready",
        qos=pubsub.QOS.AT_LEAST_ONCE,
        retain=True,
    )

    try:

        logger.debug("Starting od_blank.")
        logger.info("Starting reading of blank OD. This will take less than a minute.")

        if (
            ("stirring" not in pio_jobs_running())
            # but if test mode, ignore
            and not is_testing_env()
        ):
            logger.error("stirring should be running. Run stirring first.")
            raise ValueError("stirring should be running. Run stirring first.")

        # running this will mess with OD Reading - best to just not let it happen.
        if (
            ("od_reading" in pio_jobs_running())
            # but if test mode, ignore
            and not is_testing_env()
        ):
            logger.error("od_reading should not be running. Stop od_reading first.")
            raise ValueError("od_reading should not be running. Stop od_reading first.")

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_blank/$state",
            "ready",
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )

        # we sample faster, because we can, but we need to increase the data rate.
        # note we can't do this for od_normalization, because we need an accurate
        # estimate of variance.
        sampling_rate = 0.1

        # start od_reading
        od_reader = ODReader(
            create_channel_label_map_from_string(od_angle_channel),
            sampling_rate=sampling_rate,
            unit=unit,
            experiment=f"{experiment}-blank",
        )
        od_reader.adc_reader.data_rate = 32

        def yield_from_mqtt():
            while True:
                msg = pubsub.subscribe(
                    f"pioreactor/{unit}/{experiment}-blank/od_reading/od_raw_batched"
                )
                yield json.loads(msg.payload)

        signal = yield_from_mqtt()
        readings = defaultdict(list)

        for count, batched_reading in enumerate(signal):
            for (sensor, reading) in batched_reading.items():
                readings[sensor].append(reading)

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

        logger.info("OD blank reading finished.")

        return
    except Exception as e:
        logger.error(f"{str(e)}")
    finally:
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_blank/$state",
            "disconnected",
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )


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
