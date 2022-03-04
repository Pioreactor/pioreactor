# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from json import dumps
from typing import Optional

import click
from msgspec.json import decode

from pioreactor import pubsub
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.math_helpers import correlation
from pioreactor.utils.math_helpers import trimmed_mean
from pioreactor.utils.timing import current_utc_time
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_latest_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def od_blank(
    od_angle_channel1: pt.PdAngle,
    od_angle_channel2: pt.PdAngle,
    n_samples: int = 40,
) -> Optional[dict[pt.PdAngle, float]]:
    """
    Compute a sample average of the photodiodes attached.

    Note that because of the sensitivity of the growth rate (and normalized OD) to the starting values,
    we need a very accurate estimate of these statistics.

    There's a variance w.r.t. the rotation of the vial that we can't control.
    """
    from statistics import variance

    action_name = "od_blank"
    logger = create_logger(action_name)
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    testing_experiment = get_latest_testing_experiment_name()
    logger.info("Starting reading of blank OD. This will take about a few minutes.")

    with publish_ready_to_disconnected_state(unit, experiment, action_name):

        # running this will mess with OD Reading - best to just not let it happen.
        if (
            is_pio_job_running("od_reading")
            # but if test mode, ignore
            and not is_testing_env()
        ):
            logger.error(
                "od_reading should not be running. Stop od_reading first. Exiting."
            )
            return None

        # turn on stirring if not already on
        if not is_pio_job_running("stirring"):
            # start stirring
            st = start_stirring(
                target_rpm=config.getfloat("stirring", "target_rpm"),
                unit=unit,
                experiment=testing_experiment,
            )
            st.block_until_rpm_is_close_to_target()
        else:
            # TODO: it could be paused, we should make sure it's running
            ...

        sampling_rate = 1 / config.getfloat("od_config", "samples_per_second")

        # start od_reading
        start_od_reading(
            od_angle_channel1,
            od_angle_channel2,
            sampling_rate=sampling_rate,
            unit=unit,
            experiment=testing_experiment,
            fake_data=is_testing_env(),
        )

        def yield_from_mqtt():
            while True:
                msg = pubsub.subscribe(
                    f"pioreactor/{unit}/{testing_experiment}/od_reading/od_raw_batched"
                )
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

        means = {}
        variances = {}
        autocorrelations = {}  # lag 1

        for channel, od_reading_series in readings.items():
            # measure the mean and publish. The mean will be used to normalize the readings in downstream jobs
            means[channel] = trimmed_mean(od_reading_series)
            variances[channel] = variance(od_reading_series)
            autocorrelations[channel] = correlation(
                od_reading_series[:-1], od_reading_series[1:]
            )

            # warn users that a blank is 0 - maybe this should be an error instead? TODO: link this to a docs page.
            if means[channel] == 0.0:
                logger.warning(
                    f"OD reading for PD Channel {channel} is 0.0 - that shouldn't be. Is there a loose connection, or an extra channel in the configuration's [od_config.photodiode_channel] section?"
                )

            pubsub.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/{channel}",
                dumps({"timestamp": current_utc_time(), "od_reading_v": means[channel]}),
            )

        # store locally as the source of truth.
        with local_persistant_storage(action_name) as cache:
            cache[experiment] = dumps(means)

        # publish to UI and database
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/{action_name}/mean",
            dumps(means),
            qos=pubsub.QOS.AT_LEAST_ONCE,
            retain=True,
        )

        if config.getboolean(
            "data_sharing_with_pioreactor",
            "send_od_statistics_to_Pioreactor",
            fallback=False,
        ):
            to_share = {"mean": means, "variance": variances}
            to_share["ir_intensity"] = config["od_config"]["ir_intensity"]
            to_share["od_angle_channel1"] = od_angle_channel1  # type: ignore
            to_share["od_angle_channel2"] = od_angle_channel2  # type: ignore
            pubsub.publish_to_pioreactor_cloud("od_blank_mean", json=to_share)

        logger.debug(f"observed data: {od_reading_series}")
        logger.debug(f"measured mean: {means}")
        logger.debug(f"measured variances: {variances}")
        logger.debug(f"measured autocorrelations: {autocorrelations}")
        logger.debug("OD normalization finished.")

        return means


@click.command(name="od_blank")
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
def click_od_blank(od_angle_channel1, od_angle_channel2, n_samples):
    """
    Compute statistics about the blank OD time series
    """
    od_blank(
        od_angle_channel1,
        od_angle_channel2,
        n_samples=n_samples,
    )
