# -*- coding: utf-8 -*-
# temperature compensation
"""
What we want to end up with is a look up table that relates (temperature of vial) to (standardized optical density). For temperatures inbetween two values in the look up table, we can interpolate. Outside? I guess extrapolate...

Note that the specific temperatures in the lookup don't matter (i.e doesn't matter if it's 32.0C vs 32.05C). So we
only need to change the duty cycle, and not worry about a closed-feedback loop to target some specific temperature.


Questions include:

1. What should the angles be?
    - possibility is to use 180, and water as media.
    - 45 has been working well, since there is some stray light => can use water as media.
2. What should the media be?
8. Does a compensation need to be rerun if I replace the LED? If I move/reposition it? Over time?
 - replacing LED: certainly, especially if it's a different model
 - moving it? I don't think so
 - over time: probably pretty okay - only active ~20% of the time in an experiment, and only being driven at about 50% of max.

"""
import json, time
import click
from collections import defaultdict
from pioreactor.logging import create_logger
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.utils import (
    is_pio_job_running,
    publish_ready_to_disconnected_state,
    local_persistant_storage,
)
from pioreactor.config import config
from pioreactor.whoami import (
    get_unit_name,
    get_latest_testing_experiment_name,
    get_latest_experiment_name,
    is_testing_env,
)

from pioreactor.pubsub import subscribe_and_callback, publish_to_pioreactor_cloud


def simple_linear_regression(x, y):
    import numpy as np

    x = np.array(x)
    y = np.array(y)

    n = x.shape[0]
    assert n > 2

    sum_x = np.sum(x)
    sum_xx = np.sum(x * x)

    slope = (n * np.sum(x * y) - sum_x * np.sum(y)) / (n * sum_xx - sum_x ** 2)
    bias = y.mean() - slope * x.mean()

    residuals_sq = ((y - (slope * x + bias)) ** 2).sum()
    std_error_slope = np.sqrt(residuals_sq / (n - 2) / (np.sum((x - x.mean()) ** 2)))

    std_error_bias = np.sqrt(
        residuals_sq / (n - 2) / n * sum_xx / (np.sum((x - x.mean()) ** 2))
    )

    return (slope, std_error_slope), (bias, std_error_bias)


def od_temperature_compensation():
    import numpy as np

    action_name = "od_temperature_compensation"
    logger = create_logger(action_name)
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    testing_experiment = get_latest_testing_experiment_name()
    temps, ods = [], defaultdict(list)

    with publish_ready_to_disconnected_state(unit, experiment, action_name):

        logger.info("Starting OD temperature compensation. This will take two hours.")

        if (
            is_pio_job_running("od_reading")
            or is_pio_job_running("temperature_control")
            or is_pio_job_running("stirring")
        ):
            logger.error(
                "Make sure OD Reading, Temperature Control, and Stirring are off before running OD temperature compensation. Exiting."
            )
            return

        # start stirring
        st = Stirrer(
            config.getint("stirring", "duty_cycle"),
            unit=unit,
            experiment=testing_experiment,
        )
        st.start_stirring()

        # initialize temperature controller.
        duty_cycle = 10
        tc = TemperatureController(
            "constant_duty_cycle",
            unit=unit,
            experiment=testing_experiment,
            duty_cycle=duty_cycle,
        )

        # start od_reading
        # it's important to use od_reading (and not ADCReader) because we want to mimic
        # production environment as closely as possible (i.e. same LED behaviours, same sampling, etc)
        od_reader = start_od_reading(
            config.get("od_config.photodiode_channel", "0", fallback=None),
            config.get("od_config.photodiode_channel", "1", fallback=None),
            config.get("od_config.photodiode_channel", "2", fallback=None),
            config.get("od_config.photodiode_channel", "3", fallback=None),
            sampling_rate=1
            / config.getfloat("od_config.od_sampling", "samples_per_second"),
            unit=unit,
            experiment=testing_experiment,
            fake_data=is_testing_env(),
        )
        # turn off the built in temperature compensator
        od_reader.temperature_compensator.compensate_od_for_temperature = (
            lambda od, *args, **kwargs: od
        )
        time.sleep(1)

        def record_od(message):
            if message.payload:

                temp = json.loads(message.payload)["temperature"]

                temps.append(temp)
                for channel in od_reader.channel_angle_map.keys():
                    ods[channel].append(od_reader.latest_reading[channel])

        # I want to listen for new temperatures coming in, and when I observe one, take od reading
        subscribe_and_callback(
            record_od,
            f"pioreactor/{unit}/{testing_experiment}/temperature_control/temperature",
        )
        for i in range(10):
            # sleep for a while?
            time.sleep(60 * 13)

            # update heater, to get new temps
            duty_cycle += 4
            tc.temperature_automation_job.set_duty_cycle(duty_cycle)

        for channel, angle in od_reader.channel_angle_map.items():

            log_ods = np.log(ods[channel])
            (temp_coef, std_error_temp_coef), _ = simple_linear_regression(
                x=temps, y=log_ods
            )
            logger.debug(
                f"{channel}, {angle}: temp_coef={temp_coef}, std_error_temp_coef={std_error_temp_coef}"
            )

            with local_persistant_storage("od_temperature_compensation") as cache:
                cache["log_linear"] = json.dumps(
                    {"estimate": temp_coef, "std_error": std_error_temp_coef}
                )

            if config.getboolean(
                "data_sharing_with_pioreactor", "send_od_statistics_to_Pioreactor"
            ):
                to_share = dict(zip(temps, ods))
                to_share["ir_led_part_number"] = config["od_config"]["ir_led_part_number"]
                to_share["ir_intensity"] = config["od_config.od_sampling"]["ir_intensity"]
                to_share["angle"] = angle

                publish_to_pioreactor_cloud(
                    "od_temperature_compensation",
                    json=to_share,
                )

        logger.info("Finished OD temperature compensation.")


@click.command(name="od_temperature_compensation")
def click_od_temperature_compensation():
    """
    Generate a OD vs. Temperature compensation value.
    """
    od_temperature_compensation()
