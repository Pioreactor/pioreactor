# -*- coding: utf-8 -*-
"""

Publishes a message like:

    {'0': 1.3e-5, '1': 3.2e-6}

to the topic

  pioreactor/{unit}/{experiment}/od_normalization/mean

and

  pioreactor/{unit}/{experiment}/od_normalization/variance





"""
import json
from collections import defaultdict

import click

from pioreactor.config import config
from pioreactor.utils import (
    is_pio_job_running,
    publish_ready_to_disconnected_state,
    local_persistant_storage,
)
from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor import pubsub
from pioreactor.logging import create_logger


def od_normalization(unit=None, experiment=None, n_samples=35):
    from statistics import mean, variance

    action_name = "od_normalization"
    logger = create_logger(action_name)
    logger.debug("Starting OD normalization.")

    with publish_ready_to_disconnected_state(unit, experiment, action_name):

        if (
            not (is_pio_job_running("od_reading"))
            # but if test mode, ignore
            and not is_testing_env()
        ):
            logger.error(" OD Reading should be running. Run OD Reading first. Exiting.")
            raise ValueError(
                "OD Reading should be running. Run OD Reading first. Exiting."
            )

        # TODO: write tests for this
        def yield_from_mqtt():
            while True:
                msg = pubsub.subscribe(
                    f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                    allow_retained=False,
                )
                yield json.loads(msg.payload)

        signal = yield_from_mqtt()
        readings = defaultdict(list)

        try:

            for count, batched_reading in enumerate(signal):
                for (sensor, reading) in batched_reading["od_raw"].items():
                    readings[sensor].append(reading["voltage"])

                pubsub.publish(
                    f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                    count / n_samples * 100,
                )
                print(f"Progress: {count/n_samples:.0%}")
                if count == n_samples:
                    break
            variances = {}
            means = {}

            for sensor, reading_series in readings.items():
                # measure the variance and publish. The variance will be used in downstream jobs.
                variances[sensor] = variance(reading_series)
                # measure the mean and publish. The mean will be used to normalize the readings in downstream jobs
                means[sensor] = mean(reading_series)

            with local_persistant_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps(means)

            with local_persistant_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps(variances)

            logger.debug(f"measured mean: {means}")
            logger.debug(f"measured variances: {variances}")
            logger.debug("OD normalization finished.")

            if config.getboolean(
                "data_sharing_with_pioreactor",
                "send_od_statistics_to_Pioreactor",
                fallback=False,
            ):

                add_on = {
                    "ir_led_part_number": config["od_config"]["ir_led_part_number"],
                    "ir_intensity": config["od_config.od_sampling"]["ir_intensity"],
                }

                pubsub.publish_to_pioreactor_cloud(
                    "od_normalization_variance",
                    json={
                        **variances,
                        **add_on,
                    },  # TODO: this syntax changed in a recent python version...
                )
                pubsub.publish_to_pioreactor_cloud(
                    "od_normalization_mean",
                    json={**means, **add_on},
                )

            return means, variances

        except Exception as e:
            logger.debug(e, exc_info=True)
            logger.error(f"{str(e)}")


@click.command(name="od_normalization")
@click.option(
    "--n-samples",
    default=30,
    show_default=True,
    help="Number of samples",
)
def click_od_normalization(n_samples):
    """
    Compute statistics about the OD timeseries
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    print(od_normalization(n_samples, unit, experiment))
