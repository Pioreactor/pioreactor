# -*- coding: utf-8 -*-
import json

import click

from pioreactor.config import config
from pioreactor.utils import pio_jobs_running
from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor import pubsub
from pioreactor.logging import create_logger
from pioreactor.background_jobs.od_reading import ODReader, create_channel_angle_map


def od_blank(od_angle_channels, unit=None, experiment=None, N_samples=30):
    from statistics import mean
    from collections import defaultdict

    action_name = "od_blank"
    logger = create_logger(action_name)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/{action_name}/$state",
        "ready",
        qos=pubsub.QOS.AT_LEAST_ONCE,
        retain=True,
    )

    try:

        logger.debug(f"Starting {action_name}.")
        logger.info("Starting reading of blank OD. This will take less than a minute.")

        # running this will mess with OD Reading - best to just not let it happen.
        if (
            ("od_reading" in pio_jobs_running())
            # but if test mode, ignore
            and not is_testing_env()
        ):
            logger.error("od_reading should not be running. Stop od_reading first.")
            raise ValueError("od_reading should not be running. Stop od_reading first.")

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/{action_name}/$state",
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
            create_channel_angle_map(*od_angle_channels),
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
            for (sensor, reading) in batched_reading["od_raw"].items():
                readings[sensor].append(reading["voltage"])

            if count == N_samples:
                break

        means = {}
        for sensor, reading_series in readings.items():
            # measure the mean and publish. The mean will be used to normalize the readings in downstream jobs
            means[sensor] = mean(reading_series)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/{action_name}/mean",
            json.dumps(means),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )

        if config.getboolean(
            "data_sharing_with_pioreactor",
            "send_od_statistics_to_Pioreactor",
            fallback=False,
        ):
            # TODO: build this service!
            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/mean",
                mean,
                hostname="mqtt.pioreactor.com",
            )

        logger.info("OD blank reading finished.")

        return
    except Exception as e:
        logger.debug(e, exc_info=True)
        logger.error(e)
    finally:
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/{action_name}/$state",
            "disconnected",
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )


@click.command(name="od_blank")
@click.option(
    "--od-angle-channel0",
    default=config.get("od_config.photodiode_channel", "0", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 0, separated by commas. Don't specify if channel is empty.",
)
@click.option(
    "--od-angle-channel1",
    default=config.get("od_config.photodiode_channel", "1", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 1, separated by commas. Don't specify if channel is empty.",
)
@click.option(
    "--od-angle-channel2",
    default=config.get("od_config.photodiode_channel", "2", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 2, separated by commas. Don't specify if channel is empty.",
)
@click.option(
    "--od-angle-channel3",
    default=config.get("od_config.photodiode_channel", "3", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 3, separated by commas. Don't specify if channel is empty.",
)
def click_od_blank(
    od_angle_channel0, od_angle_channel1, od_angle_channel2, od_angle_channel3
):
    """
    Compute statistics about the blank OD timeseries
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    od_blank(
        [od_angle_channel0, od_angle_channel1, od_angle_channel2, od_angle_channel3],
        unit,
        experiment,
    )
