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
from pioreactor.background_jobs.od_reading import ADCReader, PD_CHANNELS
from pioreactor.utils import correlation
from pioreactor.pubsub import publish
from pioreactor.logging import create_logger
from pioreactor.actions.led_intensity import led_intensity, LED_CHANNELS
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

    INTENSITIES = list(range(2, 51, 8))
    current_experiment_name = get_latest_experiment_name()
    results = {}
    try:
        adc_reader = ADCReader(
            channels=PD_CHANNELS,
            unit=unit,
            experiment=experiment,
            dynamic_gain=False,
            initial_gain=16,  # I think a small gain is okay, since we only varying the lower-end of LED intensity
            fake_data=is_testing_env(),
        )
        adc_reader.setup_adc()

        # set all to 0, but use original experiment name, since we indeed are setting them to 0.
        for led_channel in LED_CHANNELS:
            assert led_intensity(
                led_channel,
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

    for led_channel in LED_CHANNELS:
        logger.debug(f"Varying intensity of channel {led_channel}.")
        varying_intensity_results = defaultdict(list)
        for intensity in INTENSITIES:
            # turn on the LED to set intensity
            led_intensity(
                led_channel,
                intensity=intensity,
                unit=unit,
                experiment=current_experiment_name,
                verbose=False,
            )

            # record from ADC
            readings = adc_reader.take_reading()

            # Add to accumulating list
            for pd_channel in PD_CHANNELS:
                varying_intensity_results[pd_channel].append(readings[pd_channel])

        # compute the linear correlation between the intensities and observed PD measurements

        for pd_channel in PD_CHANNELS:
            results[(led_channel, pd_channel)] = round(
                correlation(INTENSITIES, varying_intensity_results[pd_channel]), 2
            )

        # set back to 0
        led_intensity(
            led_channel,
            intensity=0,
            unit=unit,
            experiment=current_experiment_name,
            verbose=False,
        )

    logger.debug(f"Correlations between LEDs and PD:\n{pformat(results)}")
    detected_relationships = []
    for pair, measured_correlation in results.items():
        if measured_correlation > 0.85:
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

    # test ambiant light interference. With all LEDs off, we should see near 0 light.
    readings = adc_reader.take_reading()
    print(readings)
    publish(
        f"pioreactor/{unit}/{experiment}/self_test/ambiant_light_interference",
        int(all([readings[pd_channel] < 0.001 for pd_channel in PD_CHANNELS])),
        retain=False,
    )

    return detected_relationships


def self_test():

    unit = get_unit_name()
    experiment = get_latest_testing_experiment_name()
    logger = create_logger(
        "self_test", unit=unit, experiment=get_latest_experiment_name()
    )

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
