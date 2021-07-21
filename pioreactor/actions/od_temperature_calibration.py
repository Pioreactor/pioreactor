# -*- coding: utf-8 -*-
# temperature compensation
"""
What we want to end up with is a look up table that relates (temperature of vial) to (standardized optical density). For temperatures inbetween two values in the look up table, we can interpolate. Outside? I guess extrapolate...

Note that the specific temperatures in the lookup don't matter (i.e doesn't matter if it's 32.0C vs 32.05C). So we
only need to change the duty cycle, and not worry about a closed-feedback loop to target some specific temperature.


Questions include:

1. What should the angles be?
2. What should the media be?
3. Should stirring be on?
    - probably, as this mimics production more, and will distribute heating more.
4. How many data points should we keep?
5. Where do we store the lookup table?
    - DBM, but _not_ in /tmp..., I guess in ~/.pioreactor/

6. How we do share with Pioreactor, the company?
7. Where is it in the UI?
  - calibration popup
8. Does a calibration need to be rerun if I replace the LED? If I move/reposition it?

"""
import json, time
import click
from pioreactor.logging import create_logger
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.background_jobs.od_reading import ODReader, create_channel_angle_map
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.utils import is_pio_job_running, publish_ready_to_disconnected_state
from pioreactor.config import config
from pioreactor.whoami import (
    get_unit_name,
    get_latest_testing_experiment_name,
    get_latest_experiment_name,
    is_testing_env,
)

from pioreactor.pubsub import publish, subscribe_and_callback


def od_temperature_calibration():

    action_name = "od_temperature_calibration"
    logger = create_logger(action_name)
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    testing_experiment = get_latest_testing_experiment_name()

    with publish_ready_to_disconnected_state(unit, experiment, action_name):

        if (
            is_pio_job_running("od_reading")
            or is_pio_job_running("temperature_control")
            or is_pio_job_running("stirring")
        ):
            logger.error(
                "Make sure OD Reading, Temperature Control, and Stirring are off before running OD temperature calibration. Exiting."
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
        duty_cycle = 20
        tc = TemperatureController(
            "constant_duty_cycle", unit=unit, experiment=testing_experiment, duty_cycle=20
        )

        # start od_reading
        od_reader = ODReader(
            create_channel_angle_map("90", None, None, None),  # TODO: formalize this.
            sampling_rate=1
            / config.getfloat("od_config.od_sampling", "samples_per_second"),
            unit=unit,
            experiment=testing_experiment,
            fake_data=is_testing_env(),
        )

        def record_od(message):
            if message.payload:
                # requires reading the raw ADC values, and not the ones produced by OD reading - as they are already temperature compensated.
                latest_adc_reading = od_reader.adc_reader.A0["voltage"]

                temp = json.loads(message.payload)["temperature"]

                temp_od_lookup[temp] = latest_adc_reading
                logger.debug(temp_od_lookup)

        # I want to listen for new temperatures coming in, and when I observe one, take od reading
        subscribe_and_callback(
            record_od,
            f"pioreactor/{unit}/{testing_experiment}/temperature_control/temperature",
        )

        # sleep for a while?
        time.sleep(60 * 25)

        # update heater, to get new temps
        duty_cycle = 40
        tc.temperature_automation_job.set_duty_cycle(duty_cycle)

        # sleep for a while?
        time.sleep(60 * 25)

        # save lookup - where?
        logger.debug(temp_od_lookup)
        with open("~/.pioreactor/od_temperature_calibration.json", "w") as f:
            json.dump(temp_od_lookup, f, indent=2)

        if config.getboolean(
            "data_sharing_with_pioreactor", "send_od_statistics_to_Pioreactor"
        ):
            publish(
                "pioreactor/od_temperature_calibration",
                json.dumps(temp_od_lookup),
                hostname="mqtt.pioreactor.com",
            )


@click.command(name="od_temperature_calibration")
def click_od_temperature_calibration():
    """
    Check the IO in the Pioreactor
    """
    od_temperature_calibration()
