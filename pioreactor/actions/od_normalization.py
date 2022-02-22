# -*- coding: utf-8 -*-
"""

Publishes a message like:

    {'0': 1.3e-5, '1': 3.2e-6}

to the topic

  pioreactor/{unit}/{experiment}/od_normalization/mean

and

  pioreactor/{unit}/{experiment}/od_normalization/variance

"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Generator

import click

from pioreactor import exc
from pioreactor import pubsub
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.types import PdChannel
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.math_helpers import correlation
from pioreactor.utils.math_helpers import residuals_of_simple_linear_regression
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def od_normalization(
    unit: str, experiment: str, n_samples: int = 35
) -> tuple[dict[PdChannel, float], dict[PdChannel, float]]:
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
            raise exc.JobRequiredError(
                "OD Reading should be running. Run OD Reading first. Exiting."
            )

        # TODO: write tests for this
        def yield_from_mqtt() -> Generator[dict, None, None]:
            while True:
                msg = pubsub.subscribe(
                    f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                    allow_retained=False,
                )
                if msg is None:
                    continue

                yield json.loads(msg.payload)

        signal = yield_from_mqtt()
        readings = defaultdict(list)

        for count, batched_reading in enumerate(signal, start=1):
            for (sensor, reading) in batched_reading["od_raw"].items():
                readings[sensor].append(reading["voltage"])

            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                count // n_samples * 100,
            )
            logger.debug(f"Progress: {count/n_samples:.0%}")
            if count == n_samples:
                break

        def trimmed_mean(x: list) -> float:
            x = list(x)  # copy it
            max_, min_ = max(x), min(x)
            x.remove(max_)
            x.remove(min_)
            return mean(x)

        variances = {}
        means = {}
        autocorrelations = {}  # lag 1

        for sensor, od_reading_series in readings.items():
            variances[sensor] = variance(
                residuals_of_simple_linear_regression(
                    list(range(n_samples)), od_reading_series
                )
            )  # see issue #206
            means[sensor] = trimmed_mean(od_reading_series)
            autocorrelations[sensor] = correlation(
                od_reading_series[:-1], od_reading_series[1:]
            )

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps(means)

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps(variances)

        logger.debug(f"observed data: {od_reading_series}")
        logger.debug(f"measured mean: {means}")
        logger.debug(f"measured variances: {variances}")
        logger.debug(f"measured autocorrelations: {autocorrelations}")
        logger.debug("OD normalization finished.")

        if config.getboolean(
            "data_sharing_with_pioreactor",
            "send_od_statistics_to_Pioreactor",
            fallback=False,
        ):

            add_on = {
                "ir_intensity": config["od_config"]["ir_intensity"],
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


@click.command(name="od_normalization")
@click.option(
    "--n-samples",
    default=30,
    show_default=True,
    help="Number of samples",
)
def click_od_normalization(n_samples):
    """
    Compute statistics about the OD time series
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    click.echo(od_normalization(unit, experiment, n_samples=n_samples))
