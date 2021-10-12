# -*- coding: utf-8 -*-
"""
This action performs internal hardware & software tests of the system to confirm things work as expected.

Functions with prefix `test_` are ran, and an Exception thrown means the test failed.

Outputs from each test go into MQTT, and return to the command line.
"""

import time, sys
from json import dumps
import click
from pioreactor.whoami import (
    get_unit_name,
    get_latest_testing_experiment_name,
    get_latest_experiment_name,
    is_testing_env,
)
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.background_jobs.od_reading import ADCReader, PD_CHANNELS
from pioreactor.utils.math_helpers import correlation
from pioreactor.pubsub import publish
from pioreactor.logging import create_logger
from pioreactor.actions.led_intensity import led_intensity, LED_CHANNELS
from pioreactor.utils import is_pio_job_running, publish_ready_to_disconnected_state
from pioreactor.background_jobs import stirring
from pioreactor.config import config


def test_pioreactor_hat_present(logger, unit, experiment):
    try:
        adc_reader = ADCReader(
            channels=PD_CHANNELS,
            dynamic_gain=False,
            initial_gain=16,
            fake_data=is_testing_env(),
        )
        adc_reader.setup_adc()
    except (AssertionError, OSError):
        assert False
    else:
        assert True


def test_all_positive_correlations_between_pds_and_leds(logger, unit, experiment):
    """
    This tests that there is a positive correlation between the IR LED channel, and the photodiodes
    as defined in the config.ini.
    """
    from pprint import pformat

    INTENSITIES = list(
        range(2, 59, 7)
    )  # better to err on the side of MORE samples than less - it's only a few extra seconds...
    current_experiment_name = get_latest_experiment_name()
    results = {}

    adc_reader = ADCReader(
        channels=PD_CHANNELS,
        dynamic_gain=False,
        initial_gain=16,  # I think a small gain is okay, since we only varying the lower-end of LED intensity
        fake_data=is_testing_env(),
    )

    adc_reader.setup_adc()

    # set all to 0, but use original experiment name, since we indeed are setting them to 0.
    for led_channel in LED_CHANNELS:
        led_intensity(
            led_channel,
            intensity=0,
            unit=unit,
            source_of_event="self_test",
            experiment=current_experiment_name,
            verbose=False,
        )

    for led_channel in LED_CHANNELS:
        varying_intensity_results = {pd_channel: [] for pd_channel in PD_CHANNELS}
        for intensity in INTENSITIES:
            # turn on the LED to set intensity
            led_intensity(
                led_channel,
                intensity=intensity,
                unit=unit,
                experiment=current_experiment_name,
                verbose=False,
                source_of_event="self_test",
            )

            # record from ADC, we'll average them
            readings1 = adc_reader.take_reading()
            readings2 = adc_reader.take_reading()

            # Add to accumulating list
            for pd_channel in PD_CHANNELS:
                varying_intensity_results[pd_channel].append(
                    0.5 * (readings1[pd_channel] + readings2[pd_channel])
                )

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
            source_of_event="self_test",
        )

    logger.debug(f"Correlations between LEDs and PD:\n{pformat(results)}")
    detected_relationships = []
    for pair, measured_correlation in results.items():
        if measured_correlation > 0.85:
            detected_relationships.append(pair)

    publish(
        f"pioreactor/{unit}/{experiment}/self_test/correlations_between_pds_and_leds",
        dumps(detected_relationships),
        retain=True,
    )

    # we require that the IR photodiodes defined in the config have a
    # correlation with the IR led
    pd_channels_to_test = [
        int(ch)
        for (ch, angle) in config["od_config.photodiode_channel"].items()
        if angle != ""
    ]

    # also check if we have a REF channel
    if config.getint("od_config", "ir_led_output_channel"):
        pd_channels_to_test.append(config.getint("od_config", "ir_led_output_channel"))

    ir_led_channel = config["leds_reverse"]["ir_led"]

    for ir_pd_channel in pd_channels_to_test:
        assert (
            results[(ir_led_channel, ir_pd_channel)] > 0.85
        ), f"missing {ir_led_channel} ⇝ {ir_pd_channel}"


def test_ambient_light_interference(logger, unit, experiment):
    # test ambient light IR interference. With all LEDs off, and the Pioreactor not in a sunny room, we should see near 0 light.
    # TODO: it's never 0 because of the common current problem.

    # A "sunlight" be useful is detecting a high autocorrelation of the PD signal when LED%=0. Sunlight tends to increase and decrease
    # with cloud cover. This requires us to take a time series of data points though...

    adc_reader = ADCReader(
        channels=PD_CHANNELS,
        dynamic_gain=False,
        initial_gain=16,
        fake_data=is_testing_env(),
    )

    adc_reader.setup_adc()

    for led_channel in LED_CHANNELS:
        led_intensity(
            led_channel,
            intensity=0,
            unit=unit,
            source_of_event="self_test",
            experiment=experiment,
            verbose=False,
        )

    readings = adc_reader.take_reading()

    assert all([readings[pd_channel] < 0.005 for pd_channel in PD_CHANNELS]), readings


def test_detect_heating_pcb(logger, unit, experiment):
    try:
        with TemperatureController("silent", unit=unit, experiment=experiment):
            ...
    except IOError:
        assert False
    else:
        assert True


def test_positive_correlation_between_temp_and_heating(logger, unit, experiment):
    with TemperatureController("silent", unit=unit, experiment=experiment) as tc:

        measured_pcb_temps = []
        dcs = list(range(0, 48, 6))
        logger.debug("Varying heating.")
        for dc in dcs:
            tc._update_heater(dc)
            time.sleep(0.75)
            measured_pcb_temps.append(tc.read_external_temperature())

        tc._update_heater(0)
        measured_correlation = round(correlation(dcs, measured_pcb_temps), 2)
        logger.debug(
            f"Correlation between temp sensor and heating: {measured_correlation}"
        )
        assert measured_correlation > 0.9, (dcs, measured_pcb_temps)


def test_positive_correlation_between_rpm_and_stirring(logger, unit, experiment):
    dcs = list(range(90, 50, -5))
    measured_rpms = []

    rpm_calc = stirring.RpmFromFrequency()

    st = stirring.Stirrer(
        target_rpm=400, unit=unit, experiment=experiment, rpm_calculator=None
    )
    st.duty_cycle = dcs[0]

    st.start_stirring()
    time.sleep(2)

    for dc in dcs:
        st.set_duty_cycle(dc)
        time.sleep(1)
        measured_rpms.append(rpm_calc(4))

    rpm_calc.cleanup()

    measured_correlation = round(correlation(dcs, measured_rpms), 2)
    logger.debug(
        f"Correlation between stirring RPM and duty cycle: {measured_correlation}"
    )
    assert measured_correlation > 0.9, (dcs, measured_rpms)


@click.command(name="self_test")
@click.option("-k", help="see pytest's k argument", type=str)
def click_self_test(k):
    """
    Test the input/output in the Pioreactor
    """

    unit = get_unit_name()
    testing_experiment = get_latest_testing_experiment_name()
    experiment = get_latest_experiment_name()
    logger = create_logger("self_test", unit=unit, experiment=experiment)

    with publish_ready_to_disconnected_state(
        unit, get_latest_testing_experiment_name(), "self_test"
    ):

        if is_pio_job_running("od_reading", "temperature_control", "stirring"):
            logger.error(
                "Make sure OD Reading, Temperature Control, and Stirring are off before running a self test. Exiting."
            )
            return 1

        functions_to_test = [
            (name, f)
            for (name, f) in vars(sys.modules[__name__]).items()
            if name.startswith("test_")
        ]  # automagically finds the test_ functions.
        if k:
            functions_to_test = [
                (name, f) for (name, f) in functions_to_test if (k in name)
            ]

        # clear the mqtt cache
        for name, _ in functions_to_test:
            publish(
                f"pioreactor/{unit}/{testing_experiment}/self_test/{name}",
                None,
                retain=True,
            )

        count_tested = 0
        count_passed = 0
        for name, test in functions_to_test:

            try:
                test(logger, unit, testing_experiment)
            except Exception as e:
                print(e)
                res = False
            else:
                res = True

            logger.debug(f"{name}: {'✅' if res else '❌'}")

            count_tested += 1
            count_passed += res

            publish(
                f"pioreactor/{unit}/{testing_experiment}/self_test/{name}",
                int(res),
                retain=True,
            )

        publish(
            f"pioreactor/{unit}/{testing_experiment}/self_test/all_tests_passed",
            int(count_passed == count_tested),
            retain=True,
        )

        if count_passed == count_tested:
            logger.info("All tests passed ✅")
        else:
            logger.info(
                f"{count_tested-count_passed} failed test{'s' if (count_tested-count_passed) > 1 else ''}."
            )

        return int(count_passed != count_tested)
