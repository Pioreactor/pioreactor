# -*- coding: utf-8 -*-
import json
import time
from collections import defaultdict
import click

from pioreactor.config import config
from pioreactor.utils import (
    is_pio_job_running,
    publish_ready_to_disconnected_state,
    local_persistant_storage,
)
from pioreactor.whoami import (
    get_unit_name,
    get_latest_testing_experiment_name,
    get_latest_experiment_name,
    is_testing_env,
)
from pioreactor import pubsub
from pioreactor.logging import create_logger
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring


def od_blank(
    od_angle_channel1,
    od_angle_channel2,
    od_angle_channel3,
    od_angle_channel4,
    n_samples: int = 30,
):
    """
    Compute the sample average of the photodiodes attached.

    Note that because of the sensitivity of the growth rate (and normalized OD) to the starting values,
    we need a very accurate estimate of these statistics.

    """
    from statistics import mean, variance

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
            return

        # turn on stirring if not already on
        if not is_pio_job_running("stirring"):
            # start stirring
            start_stirring(
                target_rpm=config.getint("stirring", "target_rpm"),
                unit=unit,
                experiment=testing_experiment,
            )
            time.sleep(5)
        else:
            pass
            # TODO: it could be paused, we should make sure it's running

        sampling_rate = 1 / config.getfloat("od_config", "samples_per_second")

        # start od_reading
        start_od_reading(
            od_angle_channel1,
            od_angle_channel2,
            od_angle_channel3,
            od_angle_channel4,
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

        means = {}
        variances = {}
        for sensor, reading_series in readings.items():
            # measure the mean and publish. The mean will be used to normalize the readings in downstream jobs
            means[sensor] = mean(reading_series)
            variances[str(sensor) + "_var"] = variance(reading_series)

            # warn users that a blank is 0 - maybe this should be an error instead? TODO: link this to a docs page.
            if means[sensor] == 0.0:
                logger.warning(
                    f"OD reading for PD Channel {sensor} is 0.0 - that shouldn't be. Is there a loose connection, or an extra channel in the configuration's [od_config.photodiode_channel] section?"
                )

        # store locally as the source of truth.
        with local_persistant_storage(action_name) as cache:
            cache[experiment] = json.dumps(means)

        # publish to UI - this may disappear in the future
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
            to_share = {**means, **variances}
            to_share["ir_led_part_number"] = config["od_config"]["ir_led_part_number"]
            to_share["ir_intensity"] = config["od_config"]["ir_intensity"]
            to_share["od_angle_channel1"] = od_angle_channel1
            to_share["od_angle_channel2"] = od_angle_channel2
            to_share["od_angle_channel3"] = od_angle_channel3
            to_share["od_angle_channel4"] = od_angle_channel4
            pubsub.publish_to_pioreactor_cloud("od_blank_mean", json=to_share)

        logger.info("OD blank reading finished.")

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
    "--od-angle-channel3",
    default=config.get("od_config.photodiode_channel", "3", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 3, separated by commas. Don't specify if channel is empty.",
)
@click.option(
    "--od-angle-channel4",
    default=config.get("od_config.photodiode_channel", "4", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 4, separated by commas. Don't specify if channel is empty.",
)
@click.option(
    "--n-samples",
    default=30,
    show_default=True,
    help="Number of samples",
)
def click_od_blank(
    od_angle_channel1, od_angle_channel2, od_angle_channel3, od_angle_channel4, n_samples
):
    """
    Compute statistics about the blank OD time series
    """
    click.echo(
        od_blank(
            od_angle_channel1,
            od_angle_channel2,
            od_angle_channel3,
            od_angle_channel4,
            n_samples=n_samples,
        )
    )
