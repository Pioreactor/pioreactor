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
3. Should stirring be on?
    - probably, as this mimics production more, and will distribute heating more.
4. How many data points should we keep?
5. Where do we store the lookup table?
    - DBM or JSON, but _not_ in /tmp..., I guess in ~/.pioreactor/
7. Where is it in the UI?
  - calibration modal
8. Does a compensation need to be rerun if I replace the LED? If I move/reposition it? Over time?
 - replacing LED: certainly, especially if it's a different model
 - moving it? I don't think so
 - over time: probably pretty okay - only active ~20% of the time in an experiment, and only being driven at about 50% of max.

"""
import json, time
import click
from pioreactor.logging import create_logger
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.utils import is_pio_job_running, publish_ready_to_disconnected_state
from pioreactor.config import config
from pioreactor.whoami import (
    get_unit_name,
    get_latest_testing_experiment_name,
    get_latest_experiment_name,
    is_testing_env,
)

from pioreactor.pubsub import subscribe_and_callback, publish_to_pioreactor_com


def od_temperature_compensation():

    action_name = "od_temperature_compensation"
    logger = create_logger(action_name)
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    testing_experiment = get_latest_testing_experiment_name()

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

        temp_od_lookup = {}

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
            *["90", None, None, None],
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

                temp_od_lookup[temp] = od_reader.latest_reading[0]
                logger.debug(temp_od_lookup)

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

        # save lookup - where?
        logger.debug(temp_od_lookup)
        with open("/home/pi/.pioreactor/od_temperature_compensation.json", "w") as f:
            json.dump(temp_od_lookup, f, indent="")

        if config.getboolean(
            "data_sharing_with_pioreactor", "send_od_statistics_to_Pioreactor"
        ):
            publish_to_pioreactor_com(
                "pioreactor/od_temperature_compensation",
                json.dumps(temp_od_lookup),
            )

        logger.info("Finished OD temperature compensation.")


@click.command(name="od_temperature_compensation")
def click_od_temperature_compensation():
    """
    Check the IO in the Pioreactor
    """
    od_temperature_compensation()
