# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from contextlib import nullcontext
from json import dumps
from json import loads
from typing import Iterator
from typing import Optional

import click
from msgspec.json import encode

from pioreactor import pubsub
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.logging import create_logger
from pioreactor.pubsub import prune_retained_messages
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistent_storage
from pioreactor.utils import managed_lifecycle
from pioreactor.utils import math_helpers


def od_statistics(
    od_stream: Iterator[structs.ODReadings],
    action_name: str,
    experiment: Optional[str] = None,
    unit: Optional[str] = None,
    n_samples: int = 30,
    logger=None,
) -> tuple[dict[pt.PdChannel, pt.OD], dict[pt.PdChannel, pt.OD]]:
    """
    Compute a sample statistics of the photodiodes attached.

    There's a variance w.r.t. the rotation of the vial that we can't control.
    """

    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_assigned_experiment_name(unit)
    logger = logger or create_logger(action_name, unit=unit, experiment=experiment)

    logger.info(
        f"Starting to compute statistics from OD readings. Collecting {n_samples} data points. This may take a while."
    )

    # turn on stirring if not already on
    if not is_pio_job_running("stirring"):
        from pioreactor.background_jobs.stirring import start_stirring

        logger.info("Starting stirring.")
        with temporary_config_change(config, "stirring.config", "enable_dodging_od", "False"):
            st = start_stirring(
                unit=unit,
                experiment=experiment,
            )
        st.block_until_rpm_is_close_to_target(timeout=40)  # wait for stirring to be reasonable.
    else:
        st = nullcontext()  # type: ignore

    with st:
        readings = defaultdict(list)

        # okay now start collecting
        for count, batched_reading in enumerate(od_stream, start=1):
            for channel, reading in batched_reading.ods.items():
                readings[channel].append(reading.od)

            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                int(count / n_samples * 100),
            )
            logger.debug(f"Progress: {count/n_samples:.0%}")

            if count == n_samples:
                break

        means = {}
        variances = {}

        for channel, od_reading_series in readings.items():
            # measure the mean and publish. The mean will be used to normalize the readings in downstream jobs
            assert len(od_reading_series) == n_samples
            means[channel] = math_helpers.trimmed_mean(od_reading_series, cut_off_n=2)
            variances[channel] = math_helpers.trimmed_variance(
                math_helpers.residuals_of_simple_linear_regression(
                    list(range(n_samples)), od_reading_series, trimmed=True
                ),
                cut_off_n=2,
            )  # see issue #206

            # warn users that a blank is 0 - maybe this should be an error instead? TODO: link this to a docs page.
            if means[channel] == 0.0:
                logger.warning(
                    f"OD reading for PD Channel {channel} is 0.0 - that shouldn't be. Is there a loose connection, or an extra channel in the configuration's [od_config.photodiode_channel] section?"
                )

        logger.debug(f"observed data: {od_reading_series}")
        logger.debug(f"measured mean: {means}")
        logger.debug(f"measured variances: {variances}")

        return means, variances


def delete_od_blank(unit=None, experiment=None):
    action_name = "od_blank"
    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_assigned_experiment_name(unit)

    with local_persistent_storage(action_name) as cache:
        if experiment not in cache:
            return

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/{action_name}/means",
            None,
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )

        means = loads(cache[experiment])
        for channel, mean in means.items():
            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/mean/{channel}",
                None,
                qos=pubsub.QOS.AT_LEAST_ONCE,
                retain=True,
            )

        del cache[experiment]


def od_blank(
    od_angle_channel1: pt.PdAngleOrREF,
    od_angle_channel2: pt.PdAngleOrREF,
    n_samples: int = 20,
    unit=None,
    experiment=None,
) -> dict[pt.PdChannel, pt.OD]:
    from pioreactor.background_jobs.od_reading import start_od_reading

    action_name = "od_blank"
    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_assigned_experiment_name(unit)
    testing_experiment = whoami.get_testing_experiment_name()

    logger = create_logger(action_name, unit=unit, experiment=experiment)
    logger.info("Starting blank OD calibration.")

    if is_pio_job_running("od_reading"):
        logger.error("OD Reading should be off. Perform OD Blanking _before_ OD Reading.")
        raise click.Abort

    with managed_lifecycle(unit, experiment, action_name):
        try:
            with temporary_config_change(config, "stirring.config", "enable_dodging_od", "False"):
                with start_od_reading(
                    od_angle_channel1,
                    od_angle_channel2,
                    unit=unit,
                    interval=1.5,
                    experiment=testing_experiment,  # use testing experiment to not pollute the database (and they would show up in the UI)
                    fake_data=whoami.is_testing_env(),
                    calibration=True,
                ) as od_stream:
                    # warm up OD reader
                    for count, _ in enumerate(od_stream, start=0):
                        if count == 5:
                            break

                    means, _ = od_statistics(
                        od_stream,
                        action_name,
                        unit=unit,
                        experiment=experiment,
                        n_samples=n_samples,
                        logger=logger,
                    )

        except Exception as e:
            logger.debug(e, exc_info=True)
            logger.error(e)
            raise e

        with local_persistent_storage(action_name) as cache:
            cache[experiment] = dumps(means)

        # publish to UI
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/{action_name}/means",
            encode(means),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )

        logger.info("Finished computing blank ODs.")
        prune_retained_messages(f"pioreactor/{unit}/{testing_experiment}/#")

    return means


@click.group(invoke_without_command=True, name="od_blank")
@click.pass_context
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
    "--n-samples",
    default=30,
    show_default=True,
    help="Number of samples",
)
def click_od_blank(ctx, od_angle_channel1, od_angle_channel2, n_samples: int) -> None:
    """
    Compute statistics about the blank OD time series
    """
    unit = whoami.get_unit_name()
    experiment = whoami.get_assigned_experiment_name(unit)

    if ctx.invoked_subcommand is None:
        od_blank(
            od_angle_channel1,
            od_angle_channel2,
            n_samples=n_samples,
            unit=unit,
            experiment=experiment,
        )


@click_od_blank.command(name="delete")
@click.option(
    "--experiment",
    help="delete particular experiment",
)
def click_delete_od_blank(experiment):
    unit = whoami.get_unit_name()
    experiment = experiment or whoami.get_assigned_experiment_name(unit)

    delete_od_blank(unit, experiment)
