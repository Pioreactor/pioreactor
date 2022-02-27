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

from collections import defaultdict
from json import dumps
from typing import cast
from typing import Generator

import click
from msgspec.json import decode

from pioreactor import exc
from pioreactor import pubsub
from pioreactor import structs
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.types import PdChannel
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.math_helpers import correlation
from pioreactor.utils.math_helpers import residuals_of_simple_linear_regression
from pioreactor.utils.math_helpers import trimmed_mean
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def od_normalization(
    unit: str, experiment: str, n_samples: int = 40
) -> tuple[dict[PdChannel, float], dict[PdChannel, float]]:
    from statistics import variance

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
        def yield_from_mqtt() -> Generator[structs.ODReadings, None, None]:
            while True:
                msg = pubsub.subscribe(
                    f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                    allow_retained=False,
                )
                if msg is None:
                    continue

                yield decode(msg.payload, type=structs.ODReadings)

        signal = yield_from_mqtt()
        readings = defaultdict(list)

        for count, batched_reading in enumerate(signal, start=1):
            for (channel, reading) in batched_reading.od_raw.items():
                readings[channel].append(reading.voltage)

            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                count // n_samples * 100,
            )
            logger.debug(f"Progress: {count/n_samples:.0%}")
            if count == n_samples:
                break

        variances = {}
        means = {}
        autocorrelations = {}  # lag 1

        for channel, od_reading_series in readings.items():
            channel = cast(PdChannel, channel)
            variances[channel] = variance(
                residuals_of_simple_linear_regression(
                    list(range(n_samples)), od_reading_series
                )
            )  # see issue #206
            means[channel] = trimmed_mean(od_reading_series)
            autocorrelations[channel] = correlation(
                od_reading_series[:-1], od_reading_series[1:]
            )

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = dumps(means)

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = dumps(variances)

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
