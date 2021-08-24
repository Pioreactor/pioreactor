# -*- coding: utf-8 -*-
"""
This action checks the following on the Pioreactor:

1. Heating and temperature sensor by gradually increase heating's DC, and record temperature
    [x] do we detect the heating PCB over i2c?
    [x] is there a positive correlation between heating DC and temperature?

2. LEDs and PDs, ramp up each LED's output and record outputs from PDs (from ADC)
    [x] do we measure a positive correlation between any LED output and PD?
    [x] output should be a list of pairs (LED_X, PD_Y) where a positive correlation is detected
    [x] Detect the Pioreactor HAT

3. Stirring: ramp up output voltage for stirring and record RPM
    [ ] do we measure a positive correlation between stirring voltage and RPM?


Outputs from each check go into MQTT, and return to the command line.

"""

import time
import json
import click
from collections import defaultdict
from pioreactor.whoami import (
    get_unit_name,
    get_latest_testing_experiment_name,
    get_latest_experiment_name,
    is_testing_env,
)
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.utils import correlation
from pioreactor.pubsub import publish
from pioreactor.logging import create_logger
from pioreactor.actions.led_intensity import led_intensity, CHANNELS
from pioreactor.utils import is_pio_job_running, publish_ready_to_disconnected_state


def check_temperature_and_heating(unit, experiment, logger):
    try:
        tc = TemperatureController("silent", unit=unit, experiment=experiment)
        publish(
            f"pioreactor/{unit}/{experiment}/self_test/detect_heating_pcb",
            1,
            retain=False,
        )
    except IOError:
        # no point continuing
        publish(
            f"pioreactor/{unit}/{experiment}/self_test/detect_heating_pcb",
            0,
            retain=False,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/self_test/positive_correlation_between_temp_and_heating",
            0,
            retain=False,
        )
        return

    measured_pcb_temps = []
    dcs = list(range(0, 50, 6))
    logger.debug("Varying heating.")
    for dc in dcs:
        tc._update_heater(dc)
        time.sleep(0.75)
        measured_pcb_temps.append(tc.read_external_temperature())

    tc._update_heater(0)
    measured_correlation = round(correlation(dcs, measured_pcb_temps), 2)
    logger.debug(f"Correlation between temp sensor and heating: {measured_correlation}")
    publish(
        f"pioreactor/{unit}/{experiment}/self_test/positive_correlation_between_temp_and_heating",
        int(measured_correlation > 0.9),
        retain=False,
    )

    return


def check_leds_and_pds(unit, experiment, logger):
    from pprint import pformat

    INTENSITIES = list(range(0, 48, 9))
    current_experiment_name = get_latest_experiment_name()
    results = {}
    try:
        adc_reader = ADCReader(
            channels=[0, 1, 2, 3],
            unit=unit,
            experiment=experiment,
            dynamic_gain=False,
            initial_gain=16,  # I think a small gain is okay, since we only varying the lower-end of LED intensity
            fake_data=is_testing_env(),
        )
        adc_reader.setup_adc()

        # set all to 0, but use original experiment name, since we indeed are setting them to 0.
        for channel in CHANNELS:
            assert led_intensity(
                channel,
                intensity=0,
                unit=unit,
                source_of_event="self_test",
                experiment=current_experiment_name,
                verbose=False,
            )
    except (AssertionError, OSError):
        publish(
            f"pioreactor/{unit}/{experiment}/self_test/pioreactor_hat_present",
            0,
            retain=False,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/self_test/atleast_one_correlation_between_pds_and_leds",
            0,
            retain=False,
        )
        return
    finally:
        publish(
            f"pioreactor/{unit}/{experiment}/self_test/pioreactor_hat_present",
            1,
            retain=False,
        )

    for channel in CHANNELS:
        logger.debug(f"Varying intensity of channel {channel}.")
        varying_intensity_results = defaultdict(list)
        for intensity in INTENSITIES:
            # turn on the LED to set intensity
            led_intensity(
                channel,
                intensity=intensity,
                unit=unit,
                experiment=current_experiment_name,
                verbose=False,
            )

            # record from ADC
            readings = adc_reader.take_reading()

            # Add to accumulating list
            varying_intensity_results[0].append(readings[0])
            varying_intensity_results[1].append(readings[1])
            varying_intensity_results[2].append(readings[2])
            varying_intensity_results[3].append(readings[3])

        # compute the linear correlation between the intensities and observed PD measurements
        results[(channel, 0)] = round(
            correlation(INTENSITIES, varying_intensity_results[0]), 2
        )
        results[(channel, 1)] = round(
            correlation(INTENSITIES, varying_intensity_results[1]), 2
        )
        results[(channel, 2)] = round(
            correlation(INTENSITIES, varying_intensity_results[2]), 2
        )
        results[(channel, 3)] = round(
            correlation(INTENSITIES, varying_intensity_results[3]), 2
        )

        # set back to 0
        led_intensity(
            channel,
            intensity=0,
            unit=unit,
            experiment=current_experiment_name,
            verbose=False,
        )

    logger.debug(f"Correlations between LEDs and PD: {pformat(results)}")
    detected_relationships = []
    for pair, measured_correlation in results.items():
        if measured_correlation > 0.90:
            detected_relationships.append(pair)

    publish(
        f"pioreactor/{unit}/{experiment}/self_test/atleast_one_correlation_between_pds_and_leds",
        int(len(detected_relationships) > 0),
        retain=False,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/self_test/correlations_between_pds_and_leds",
        json.dumps(detected_relationships),
        retain=False,
    )
    return detected_relationships


def self_test():

    logger = create_logger("self_test")
    unit = get_unit_name()
    experiment = get_latest_testing_experiment_name()

    with publish_ready_to_disconnected_state(unit, experiment, "self_test"):

        if (
            is_pio_job_running("od_reading")
            or is_pio_job_running("temperature_control")
            or is_pio_job_running("stirring")
        ):
            logger.error(
                "Make sure OD Reading, Temperature Control, and Stirring are off before running a self test. Exiting."
            )
            return

        # LEDs and PDs
        logger.debug("Check LEDs and PDs...")
        check_leds_and_pds(unit, experiment, logger=logger)

        # temp and heating
        logger.debug("Check temperature and heating...")
        check_temperature_and_heating(unit, experiment, logger=logger)

        # TODO: stirring
        #
        #


@click.command(name="self_test")
def click_self_test():
    """
    Check the IO in the Pioreactor
    """
    self_test()
