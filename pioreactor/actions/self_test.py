# -*- coding: utf-8 -*-
"""
This action performs internal hardware & software tests of the system to confirm things work as expected.

Functions with prefix `test_` are ran, and any exception thrown means the test failed.

Outputs from each test go into MQTT, and return to the command line.
"""
from __future__ import annotations

import sys
from json import dumps
from json import loads
from threading import Thread
from time import sleep
from typing import Callable
from typing import cast

import click

from pioreactor.actions.led_intensity import ALL_LED_CHANNELS
from pioreactor.actions.led_intensity import change_leds_intensities_temporarily
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.background_jobs import stirring
from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.background_jobs.od_reading import ALL_PD_CHANNELS
from pioreactor.background_jobs.od_reading import IR_keyword
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.config import config
from pioreactor.hardware import is_HAT_present
from pioreactor.hardware import is_heating_pcb_present
from pioreactor.hardware import voltage_in_aux
from pioreactor.logging import create_logger
from pioreactor.logging import Logger
from pioreactor.pubsub import Client
from pioreactor.types import LedChannel
from pioreactor.types import PdChannel
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils import SummableDict
from pioreactor.utils.math_helpers import correlation
from pioreactor.utils.math_helpers import trimmed_mean
from pioreactor.version import hardware_version_info
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_latest_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def test_pioreactor_HAT_present(client: Client, logger: Logger, unit: str, experiment: str) -> None:
    assert is_HAT_present()


def test_REF_is_in_correct_position(
    client: Client, logger: Logger, unit: str, experiment: str
) -> None:
    # this _also_ uses stirring to increase the variance in the non-REF, so...
    from statistics import variance

    signal1 = []
    signal2 = []

    with stirring.start_stirring(
        target_rpm=450, unit=unit, experiment=experiment
    ), start_od_reading(
        od_angle_channel1="90",
        od_angle_channel2="90",
        interval=1.15,
        unit=unit,
        fake_data=is_testing_env(),
        experiment=experiment,
        use_calibration=False,
    ) as od_stream:
        for i, reading in enumerate(od_stream):
            signal1.append(reading.ods["1"].od)
            signal2.append(reading.ods["2"].od)

            if i == 25:
                break

    norm_variance_per_channel = {
        "1": variance(signal1) / trimmed_mean(signal1) ** 2,
        "2": variance(signal2) / trimmed_mean(signal2) ** 2,
    }

    ref_channel = config["od_config.photodiode_channel_reverse"][REF_keyword]

    THRESHOLD = 1.0
    if ref_channel == "1":
        assert (
            THRESHOLD * norm_variance_per_channel["1"] < norm_variance_per_channel["2"]
        ), f"{ref_channel=}, {norm_variance_per_channel=}"

    elif ref_channel == "2":
        assert (
            THRESHOLD * norm_variance_per_channel["2"] < norm_variance_per_channel["1"]
        ), f"{ref_channel=}, {norm_variance_per_channel=}"


def test_all_positive_correlations_between_pds_and_leds(
    client, logger: Logger, unit: str, experiment: str
) -> None:
    """
    This tests that there is a positive correlation between the IR LED channel, and the photodiodes
    as defined in the config.ini.

    TODO: if this exits early, we should turn off the LEDs
    """
    from pprint import pformat

    INTENSITIES = list(
        range(10, 50, 5)
    )  # better to err on the side of MORE samples than less - it's only a few extra seconds...
    current_experiment_name = get_latest_experiment_name()
    results: dict[tuple[LedChannel, PdChannel], float] = {}

    adc_reader = ADCReader(
        channels=ALL_PD_CHANNELS,
        dynamic_gain=False,
        fake_data=is_testing_env(),
    ).setup_adc()

    # set all to 0, but use original experiment name, since we indeed are setting them to 0.
    led_intensity(
        {channel: 0 for channel in ALL_LED_CHANNELS},
        unit=unit,
        experiment=current_experiment_name,
        verbose=False,
        source_of_event="self_test",
    )

    for led_channel in ALL_LED_CHANNELS:
        varying_intensity_results: dict[PdChannel, list[float]] = {
            pd_channel: [] for pd_channel in ALL_PD_CHANNELS
        }
        for intensity in INTENSITIES:
            # turn on the LED to set intensity
            led_intensity(
                {led_channel: intensity},
                unit=unit,
                experiment=current_experiment_name,
                verbose=False,
                source_of_event="self_test",
            )

            # record from ADC, we'll average them
            readings1 = adc_reader.take_reading()
            readings2 = adc_reader.take_reading()

            # Add to accumulating list
            for pd_channel in ALL_PD_CHANNELS:
                reading = 0.5 * (readings1[pd_channel] + readings2[pd_channel])
                varying_intensity_results[pd_channel].append(reading)

        # compute the linear correlation between the intensities and observed PD measurements
        for pd_channel in ALL_PD_CHANNELS:
            measured_correlation = round(
                correlation(INTENSITIES, varying_intensity_results[pd_channel]), 2
            )
            results[(led_channel, pd_channel)] = measured_correlation
            logger.debug(f"Corr({led_channel}, {pd_channel}) = {measured_correlation}")

        # set back to 0
        led_intensity(
            {led_channel: 0},
            unit=unit,
            experiment=current_experiment_name,
            verbose=False,
            source_of_event="self_test",
        )
        adc_reader.clear_batched_readings()

    logger.debug(f"Correlations between LEDs and PD:\n{pformat(results)}")
    detected_relationships = []
    for (led_channel, pd_channel), measured_correlation in results.items():
        if measured_correlation > 0.925:
            detected_relationships.append(
                (
                    (config["leds"].get(led_channel) or led_channel),
                    (config["od_config.photodiode_channel"].get(pd_channel) or pd_channel),
                )
            )

    client.publish(
        f"pioreactor/{unit}/{experiment}/self_test/correlations_between_pds_and_leds",
        dumps(detected_relationships),
        retain=True,
    )

    # we require that the IR photodiodes defined in the config have a
    # correlation with the IR led
    pd_channels_to_test: list[PdChannel] = []
    for channel, angle_or_ref in config["od_config.photodiode_channel"].items():
        if angle_or_ref != "":
            channel = cast(PdChannel, channel)
            pd_channels_to_test.append(channel)

    ir_led_channel = cast(LedChannel, config["leds_reverse"][IR_keyword])

    for ir_pd_channel in pd_channels_to_test:
        assert (
            results[(ir_led_channel, ir_pd_channel)] > 0.925
        ), f"missing {ir_led_channel} ⇝ {ir_pd_channel}"


def test_ambient_light_interference(
    client: Client, logger: Logger, unit: str, experiment: str
) -> None:
    # test ambient light IR interference. With all LEDs off, and the Pioreactor not in a sunny room, we should see near 0 light.

    adc_reader = ADCReader(
        channels=ALL_PD_CHANNELS,
        dynamic_gain=False,
        fake_data=is_testing_env(),
    )

    adc_reader.setup_adc()
    current_experiment_name = get_latest_experiment_name()
    led_intensity(
        {channel: 0 for channel in ALL_LED_CHANNELS},
        unit=unit,
        source_of_event="self_test",
        experiment=current_experiment_name,
        verbose=False,
    )

    readings = adc_reader.take_reading()

    if hardware_version_info < (1, 1):
        assert all([readings[pd_channel] < 0.005 for pd_channel in ALL_PD_CHANNELS]), readings
    else:
        assert all(
            [readings[pd_channel] < 0.067 for pd_channel in ALL_PD_CHANNELS]
        ), readings  # saw a 0.0662 blank during testing


def test_REF_is_lower_than_0_dot_256_volts(
    client, logger: Logger, unit: str, experiment: str
) -> None:
    reference_channel = cast(PdChannel, config["od_config.photodiode_channel_reverse"][REF_keyword])
    ir_channel = cast(LedChannel, config["leds_reverse"][IR_keyword])
    ir_intensity = config.getfloat("od_config", "ir_led_intensity")

    adc_reader = ADCReader(
        channels=[reference_channel],
        dynamic_gain=False,
        fake_data=is_testing_env(),
    ).setup_adc()

    current_experiment_name = get_latest_experiment_name()
    with change_leds_intensities_temporarily(
        {ir_channel: ir_intensity},
        unit=unit,
        source_of_event="self_test",
        experiment=current_experiment_name,
        verbose=False,
    ):
        readings = adc_reader.take_reading()

    assert (
        0.05 < readings[reference_channel] < 0.256
    ), f"Recorded {readings[reference_channel]} in REF, should ideally be between 0.05 and 0.256."


def test_detect_heating_pcb(client: Client, logger: Logger, unit: str, experiment: str) -> None:
    assert is_heating_pcb_present()


def test_positive_correlation_between_temperature_and_heating(
    client, logger: Logger, unit: str, experiment: str
) -> None:
    assert is_heating_pcb_present()

    with TemperatureController("only_record_temperature", unit=unit, experiment=experiment) as tc:
        measured_pcb_temps = []
        dcs = list(range(0, 22, 3))
        logger.debug("Varying heating.")
        for dc in dcs:
            tc._update_heater(dc)
            sleep(2.0)  # two cycles TODO: can I do 1 cycle?
            measured_pcb_temps.append(tc.read_external_temperature())

        tc._update_heater(0)
        measured_correlation = round(correlation(dcs, measured_pcb_temps), 2)
        logger.debug(f"Correlation between temp sensor and heating: {measured_correlation}")
        assert measured_correlation > 0.9, (dcs, measured_pcb_temps)


def test_aux_power_is_not_too_high(client: Client, logger: Logger, unit: str, experiment: str):
    assert voltage_in_aux() <= 18.0


def test_positive_correlation_between_rpm_and_stirring(
    client, logger: Logger, unit: str, experiment: str
) -> None:
    assert is_heating_pcb_present()
    assert voltage_in_aux() <= 18.0

    current_experiment_name = get_latest_experiment_name()

    with local_persistant_storage("stirring_calibration") as cache:
        if "linear_v1" in cache:
            parameters = loads(cache["linear_v1"])
            rpm_coef = parameters["rpm_coef"]
            intercept = parameters["intercept"]

            initial_dc = rpm_coef * 700 + intercept

        else:
            initial_dc = config.getfloat("stirring", "initial_duty_cycle")

    dcs = []
    measured_rpms = []
    n_samples = 8
    start = initial_dc * 1.2
    end = initial_dc * 0.8

    with stirring.Stirrer(
        target_rpm=0, unit=unit, experiment=current_experiment_name, rpm_calculator=None
    ) as st, stirring.RpmFromFrequency() as rpm_calc:
        rpm_calc.setup()
        st.duty_cycle = initial_dc
        st.start_stirring()
        sleep(1)

        for i in range(n_samples):
            p = i / n_samples
            dc = start * (1 - p) + p * end

            st.set_duty_cycle(dc)
            sleep(1)
            measured_rpms.append(rpm_calc(4))
            dcs.append(dc)

        measured_correlation = round(correlation(dcs, measured_rpms), 2)
        logger.debug(f"Correlation between stirring RPM and duty cycle: {measured_correlation}")
        logger.debug(f"{dcs=}, {measured_rpms=}")
        assert measured_correlation > 0.9, (dcs, measured_rpms)


class BatchTestRunner:
    def __init__(self, tests_to_run: list[Callable], *test_func_args) -> None:
        self.count_tested = 0
        self.count_passed = 0
        self.tests_to_run = tests_to_run
        self._thread = Thread(target=self._run, args=test_func_args)  # don't make me daemon: 295

    def start(self):
        self._thread.start()
        return self

    def collect(self) -> SummableDict:
        self._thread.join()
        return SummableDict({"count_tested": self.count_tested, "count_passed": self.count_passed})

    def _run(self, client, logger: Logger, unit: str, experiment_name: str) -> None:
        for test in self.tests_to_run:
            res = False
            test_name = test.__name__

            try:
                test(client, logger, unit, experiment_name)
                res = True
            except Exception as e:
                logger.debug(e, exc_info=True)

            logger.debug(f"{test_name}: {'✅' if res else '❌'}")

            self.count_tested += 1
            self.count_passed += int(res)

            client.publish(
                f"pioreactor/{unit}/{experiment_name}/self_test/{test_name}",
                int(res),
                retain=True,
            )


@click.command(name="self_test")
@click.option("-k", help="see pytest's -k argument", type=str, default="")
def click_self_test(k: str) -> int:
    """
    Test the input/output in the Pioreactor
    """
    unit = get_unit_name()
    testing_experiment = get_latest_testing_experiment_name()
    experiment = get_latest_experiment_name()
    logger = create_logger("self_test", unit=unit, experiment=experiment)
    logger.info("Starting self-test...")

    A_TESTS = [
        test_pioreactor_HAT_present,
        test_detect_heating_pcb,
        test_positive_correlation_between_temperature_and_heating,
        test_aux_power_is_not_too_high,
    ]
    B_TESTS = [
        test_all_positive_correlations_between_pds_and_leds,
        test_ambient_light_interference,
        test_REF_is_lower_than_0_dot_256_volts,
        test_REF_is_in_correct_position,
        test_positive_correlation_between_rpm_and_stirring,
    ]

    with publish_ready_to_disconnected_state(unit, testing_experiment, "self_test") as state:
        client = state.client
        if any(
            is_pio_job_running(
                ["od_reading", "temperature_control", "stirring", "dosing_control", "led_control"]
            )
        ):
            logger.error(
                "Make sure Optical Density, any automations, and Stirring are off before running a self test. Exiting."
            )
            raise click.Abort()

        # flicker to assist the user to confirm they are testing the right pioreactor.
        client.publish(f"pioreactor/{unit}/{experiment}/monitor/flicker_led_response_okay", 1)

        # automagically finds the test_ functions.
        functions_to_test = {
            f
            for (name, f) in vars(sys.modules[__name__]).items()
            if name.startswith("test_") and (k in name)
        }

        # and clear the mqtt cache first
        for f in functions_to_test:
            client.publish(
                f"pioreactor/{unit}/{testing_experiment}/self_test/{f.__name__}",
                None,
                retain=True,
            )

        # some tests can be run in parallel.
        test_args = (client, logger, unit, testing_experiment)
        RunnerA = BatchTestRunner(
            [f for f in A_TESTS if f in functions_to_test], *test_args
        ).start()
        RunnerB = BatchTestRunner(
            [f for f in B_TESTS if f in functions_to_test], *test_args
        ).start()

        results = RunnerA.collect() + RunnerB.collect()
        count_tested, count_passed = results["count_tested"], results["count_passed"]
        count_failures = count_tested - count_passed

        client.publish(
            f"pioreactor/{unit}/{testing_experiment}/self_test/all_tests_passed",
            int(count_failures == 0),
            retain=True,
        )

        if count_tested == 0:
            logger.info("No tests ran 🟡")
        elif count_failures == 0:
            logger.info("All tests passed ✅")
        elif count_failures > 0:
            logger.info(f"{count_failures} failed test{'s' if count_failures > 1 else ''} ❌")

        return int(count_failures > 0)
