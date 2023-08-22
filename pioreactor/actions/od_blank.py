# -*- coding: utf-8 -*-
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
from pioreactor.logging import create_logger
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import math_helpers
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.timing import current_utc_datetime


def od_statistics(
    od_stream: Iterator,
    action_name: str,
    experiment: Optional[str] = None,
    unit: Optional[str] = None,
    n_samples: int = 30,
    use_rpm: bool = True,
    logger=None,
) -> tuple[dict[pt.PdChannel, float], dict[pt.PdChannel, float]]:
    """
    Compute a sample statistics of the photodiodes attached.

    There's a variance w.r.t. the rotation of the vial that we can't control.
    """

    logger = logger or create_logger(action_name)
    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_latest_experiment_name()
    testing_experiment = whoami.get_latest_testing_experiment_name()
    logger.info(
        f"Starting to compute statistics from OD readings. Collecting {n_samples} data points."
    )

    # turn on stirring if not already on
    if not is_pio_job_running("stirring"):
        from pioreactor.background_jobs.stirring import start_stirring

        logger.info("Starting stirring.")
        st = start_stirring(
            target_rpm=config.getfloat("stirring", "target_rpm"),
            unit=unit,
            experiment=testing_experiment,
            use_rpm=use_rpm,
        )
        st.block_until_rpm_is_close_to_target(timeout=120)  # wait for maximum 2 minutes
    else:
        st = nullcontext()  # type: ignore

    with st:
        readings = defaultdict(list)
        angles = {}

        # okay now start collecting
        for count, batched_reading in enumerate(od_stream, start=1):
            for channel, reading in batched_reading.ods.items():
                readings[channel].append(reading.od)
                angles[channel] = reading.angle

            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                int(count / n_samples * 100),
            )
            logger.debug(f"Progress: {count/n_samples:.0%}")

            if count == n_samples:
                break

        means = {}
        variances = {}
        autocorrelations = {}  # lag 1

        for channel, od_reading_series in readings.items():
            # measure the mean and publish. The mean will be used to normalize the readings in downstream jobs
            assert len(od_reading_series) == n_samples
            means[channel] = math_helpers.trimmed_mean(od_reading_series)
            variances[channel] = math_helpers.trimmed_variance(
                math_helpers.residuals_of_simple_linear_regression(
                    list(range(n_samples)), od_reading_series, trimmed=True
                )
            )  # see issue #206
            autocorrelations[channel] = math_helpers.correlation(
                od_reading_series[:-1], od_reading_series[1:]
            )

            # warn users that a blank is 0 - maybe this should be an error instead? TODO: link this to a docs page.
            if means[channel] == 0.0:
                logger.warning(
                    f"OD reading for PD Channel {channel} is 0.0 - that shouldn't be. Is there a loose connection, or an extra channel in the configuration's [od_config.photodiode_channel] section?"
                )

        logger.debug(f"observed data: {od_reading_series}")
        logger.debug(f"measured mean: {means}")
        logger.debug(f"measured variances: {variances}")
        logger.debug(f"measured autocorrelations: {autocorrelations}")

        return means, variances


def delete_od_blank(unit=None, experiment=None):
    action_name = "od_blank"
    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_latest_experiment_name()

    with local_persistant_storage(action_name) as cache:
        if experiment not in cache:
            return

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/{action_name}/means",
            None,
            qos=pubsub.QOS.AT_LEAST_ONCE,
        )

        means = loads(cache[experiment])
        for channel, mean in means.items():
            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/mean/{channel}",
                None,
                qos=pubsub.QOS.AT_LEAST_ONCE,
            )

        del cache[experiment]


def od_blank(
    od_angle_channel1: pt.PdAngleOrREF,
    od_angle_channel2: pt.PdAngleOrREF,
    n_samples: int = 20,
    unit=None,
    experiment=None,
) -> dict[pt.PdChannel, float]:
    action_name = "od_blank"
    logger = create_logger(action_name)
    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_latest_experiment_name()
    testing_experiment = whoami.get_latest_testing_experiment_name()

    from pioreactor.background_jobs.od_reading import start_od_reading
    from pioreactor.background_jobs.stirring import start_stirring

    with publish_ready_to_disconnected_state(unit, experiment, action_name):
        with start_od_reading(
            od_angle_channel1,
            od_angle_channel2,
            unit=unit,
            interval=1.5,
            experiment=testing_experiment,
            fake_data=whoami.is_testing_env(),
        ) as od_stream, start_stirring(
            target_rpm=config.getfloat("stirring", "target_rpm"),
            unit=unit,
            experiment=testing_experiment,
        ) as st:
            # warm up OD reader
            for count, _ in enumerate(od_stream, start=0):
                if count == 5:
                    break

            st.block_until_rpm_is_close_to_target(timeout=30)

            means, _ = od_statistics(
                od_stream,
                action_name,
                unit=unit,
                experiment=experiment,
                n_samples=n_samples,
                logger=logger,
            )

            with local_persistant_storage(action_name) as cache:
                cache[experiment] = dumps(means)

            for channel, mean in means.items():
                pubsub.publish(
                    f"pioreactor/{unit}/{experiment}/{action_name}/mean/{channel}",
                    encode(
                        structs.ODReading(
                            timestamp=current_utc_datetime(),
                            channel=channel,
                            od=means[channel],
                            angle=config.get(
                                "od_config.photodiode_channel", channel, fallback=None
                            ),
                        )
                    ),
                    qos=pubsub.QOS.AT_LEAST_ONCE,
                )

            # publish to UI
            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/means",
                encode(means),
                qos=pubsub.QOS.AT_LEAST_ONCE,
                retain=True,
            )

            logger.info("Finished reading blank OD.")

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
    experiment = whoami.get_latest_experiment_name()

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
    experiment = experiment or whoami.get_latest_experiment_name()

    delete_od_blank(unit, experiment)
