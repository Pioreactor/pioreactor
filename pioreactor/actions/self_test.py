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
from typing import Iterator
from typing import Optional

import click

from pioreactor.actions.led_intensity import ALL_LED_CHANNELS
from pioreactor.actions.led_intensity import change_leds_intensities_temporarily
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.background_jobs import stirring
from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.background_jobs.od_reading import ALL_PD_CHANNELS
from pioreactor.background_jobs.od_reading import average_over_pd_channel_to_voltages
from pioreactor.background_jobs.od_reading import IR_keyword
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.config import config
from pioreactor.hardware import is_HAT_present
from pioreactor.hardware import is_heating_pcb_present
from pioreactor.hardware import voltage_in_aux
from pioreactor.logging import create_logger
from pioreactor.logging import CustomLogger
from pioreactor.pubsub import Client
from pioreactor.pubsub import prune_retained_messages
from pioreactor.types import LedChannel
from pioreactor.types import PdChannel
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import managed_lifecycle
from pioreactor.utils import SummableDict
from pioreactor.utils.math_helpers import correlation
from pioreactor.utils.math_helpers import mean
from pioreactor.utils.math_helpers import trimmed_mean
from pioreactor.utils.math_helpers import variance
from pioreactor.version import hardware_version_info
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def test_pioreactor_HAT_present(client: Client, logger: CustomLogger, unit: str, experiment: str) -> None:
    assert is_HAT_present(), "HAT is not connected"


def test_REF_is_in_correct_position(client: Client, logger: CustomLogger, unit: str, experiment: str) -> None:
    # this _also_ uses stirring to increase the variance in the non-REF.
    # The idea is to trigger stirring on and off and the REF should not see a change in signal / variance, but the other PD should.

    assert is_HAT_present(), "Hat is not detected."

    reference_channel = cast(PdChannel, config.get("od_config.photodiode_channel_reverse", REF_keyword))
    signal_channel = "2" if reference_channel == "1" else "1"

    signal1 = []
    signal2 = []

    with stirring.start_stirring(
        target_rpm=1250,
        unit=unit,
        experiment=experiment,
    ) as st, start_od_reading(
        od_angle_channel1="90",
        od_angle_channel2="90",
        interval=1.15,
        unit=unit,
        fake_data=is_testing_env(),
        experiment=experiment,
        use_calibration=False,
    ) as od_stream:
        st.block_until_rpm_is_close_to_target(abs_tolerance=150, timeout=10)

        for i, reading in enumerate(od_stream, start=1):
            signal1.append(reading.ods["1"].od)
            signal2.append(reading.ods["2"].od)

            if i % 5 == 0 and i % 2 == 0:
                st.set_state("ready")
            elif i % 5 == 0:
                st.set_state("sleeping")

            if i == 25:
                break

    norm_variance_per_channel = {
        "1": variance(signal1) / trimmed_mean(signal1) ** 2,
        "2": variance(signal2) / trimmed_mean(signal2) ** 2,
    }

    THRESHOLD = 6.0
    assert (
        THRESHOLD * norm_variance_per_channel[reference_channel] < norm_variance_per_channel[signal_channel]
    ), f"REF measured higher variance than SIGNAL. {reference_channel=}, {norm_variance_per_channel=}"


def test_all_positive_correlations_between_pds_and_leds(
    client: Client, logger: CustomLogger, unit: str, experiment: str
) -> None:
    """
    This tests that there is a positive correlation between the IR LED channel, and the photodiodes
    as defined in the config.ini.

    TODO: if this exits early, we should turn off the LEDs
    """
    from pprint import pformat

    assert is_HAT_present(), "HAT is not detected."
    # better to err on the side of MORE samples than less - it's only a few extra seconds...
    # we randomize to reduce effects of temperature
    # upper bound shouldn't be too high, as it could saturate the ADC, and lower bound shouldn't be too low, else we don't detect anything.

    # what's up with this order? We originally did a shuffle() of list(range(20, 55, 3))
    # so as to reduce the effects of temperature.
    # the problem is that if an LED is directly across from a PD, a high intensity will quickly
    # saturate it and fail the test. So we try low intensities first, and if we exceed some threshold
    # we exit before moving to the high intensities.
    INTENSITIES = (32, 35, 53, 44, 38, 47, 50, 41, 56, 59, 62, 65)

    results: dict[tuple[LedChannel, PdChannel], float] = {}

    ir_led_channel = cast(LedChannel, config["leds_reverse"][IR_keyword])

    # set all to 0,
    led_intensity(
        {channel: 0 for channel in ALL_LED_CHANNELS},
        unit=unit,
        experiment=experiment,
        verbose=False,
        source_of_event="self_test",
    )

    adc_reader = ADCReader(
        channels=ALL_PD_CHANNELS, dynamic_gain=False, fake_data=is_testing_env(), penalizer=0.0
    )
    adc_reader.add_external_logger(logger)
    adc_reader.tune_adc()
    # TODO: should we remove blank? Technically correlation is invariant to location.

    with stirring.start_stirring(
        target_rpm=1250,
        unit=unit,
        experiment=experiment,
    ) as st:
        st.block_until_rpm_is_close_to_target(abs_tolerance=150, timeout=10)
        # for led_channel in ALL_LED_CHANNELS: # we use to check all LED channels, but most users don't need to check all, also https://github.com/Pioreactor/pioreactor/issues/445
        for led_channel in [ir_led_channel]:  # fast to just check IR
            varying_intensity_results: dict[PdChannel, list[float]] = {
                pd_channel: [] for pd_channel in ALL_PD_CHANNELS
            }
            for intensity in INTENSITIES:
                # turn on the LED to set intensity
                led_intensity(
                    {led_channel: intensity},
                    unit=unit,
                    experiment=experiment,
                    verbose=False,
                    source_of_event="self_test",
                )

                # record from ADC, we'll average them
                avg_reading = average_over_pd_channel_to_voltages(
                    adc_reader.take_reading(), adc_reader.take_reading(), adc_reader.take_reading()
                )

                # Add to accumulating list
                for pd_channel in ALL_PD_CHANNELS:
                    varying_intensity_results[pd_channel].append(avg_reading[pd_channel])

                    if avg_reading[pd_channel] >= 2.0:
                        # we are probably going to saturate the PD - clearly we are detecting something though!
                        logger.debug(
                            f"Saw {avg_reading[pd_channel]:.2f} for pair pd_channel={pd_channel}, led_channel={led_channel}@intensity={intensity}. Saturation possible. No solution implemented yet! See issue #445"
                        )

        # compute the linear correlation between the intensities and observed PD measurements
        for pd_channel in ALL_PD_CHANNELS:
            measured_correlation = round(correlation(INTENSITIES, varying_intensity_results[pd_channel]), 2)
            results[(led_channel, pd_channel)] = measured_correlation
            logger.debug(f"Corr({led_channel}, {pd_channel}) = {measured_correlation}")
            logger.debug(list(zip(INTENSITIES, varying_intensity_results[pd_channel])))

        # set back to 0
        led_intensity(
            {led_channel: 0},
            unit=unit,
            experiment=experiment,
            verbose=False,
            source_of_event="self_test",
        )
        adc_reader.clear_batched_readings()

    logger.debug(f"Correlations between LEDs and PD:\n{pformat(results)}")
    detected_relationships = []
    for (led_channel, pd_channel), measured_correlation in results.items():
        if measured_correlation > 0.90:
            detected_relationships.append(
                (
                    (config["leds"].get(led_channel) or led_channel),
                    (config["od_config.photodiode_channel"].get(pd_channel) or pd_channel),
                )
            )

    client.publish(
        f"pioreactor/{unit}/{get_assigned_experiment_name(unit)}/self_test/correlations_between_pds_and_leds",
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

    for ir_pd_channel in pd_channels_to_test:
        assert (
            results[(ir_led_channel, ir_pd_channel)] >= 0.90
        ), f"missing {ir_led_channel} ⇝ {ir_pd_channel}, correlation: {results[(ir_led_channel, ir_pd_channel)]:0.2f}"


def test_ambient_light_interference(client: Client, logger: CustomLogger, unit: str, experiment: str) -> None:
    # test ambient light IR interference. With all LEDs off, and the Pioreactor not in a sunny room, we should see near 0 light.
    assert is_HAT_present(), "HAT is not detected."
    adc_reader = ADCReader(
        channels=ALL_PD_CHANNELS,
        dynamic_gain=False,
        fake_data=is_testing_env(),
    )

    adc_reader.add_external_logger(logger)
    adc_reader.tune_adc()
    led_intensity(
        {channel: 0 for channel in ALL_LED_CHANNELS},
        unit=unit,
        source_of_event="self_test",
        experiment=experiment,
        verbose=False,
    )

    readings = adc_reader.take_reading()

    if hardware_version_info < (1, 1):
        assert all([readings[pd_channel] < 0.005 for pd_channel in ALL_PD_CHANNELS]), readings
    else:
        assert all(
            [readings[pd_channel] < 0.080 for pd_channel in ALL_PD_CHANNELS]
        ), f"Dark signal too high: {readings=}"  # saw a 0.072 blank during testing


def test_REF_is_lower_than_0_dot_256_volts(
    client: Client, logger: CustomLogger, unit: str, experiment: str
) -> None:
    reference_channel = cast(PdChannel, config.get("od_config.photodiode_channel_reverse", REF_keyword))
    ir_channel = cast(LedChannel, config["leds_reverse"][IR_keyword])
    config_ir_intensity = config.get("od_config", "ir_led_intensity")
    if config_ir_intensity == "auto":
        ir_intensity = 50.0  # this has been our historical default, and should generally work. Default now is "auto", which targets 0.225 V into REF
    else:
        ir_intensity = float(config_ir_intensity)

    adc_reader = ADCReader(
        channels=[reference_channel], dynamic_gain=False, fake_data=is_testing_env(), penalizer=0.0
    )
    adc_reader.add_external_logger(logger)
    adc_reader.tune_adc()

    with change_leds_intensities_temporarily(
        {"A": 0, "B": 0, "C": 0, "D": 0},
        unit=unit,
        source_of_event="self_test",
        experiment=experiment,
        verbose=False,
    ):
        blank_reading = adc_reader.take_reading()
        adc_reader.set_offsets(blank_reading)  # set dark offset
        adc_reader.clear_batched_readings()

    with change_leds_intensities_temporarily(
        {ir_channel: ir_intensity},
        unit=unit,
        source_of_event="self_test",
        experiment=experiment,
        verbose=False,
    ):
        samples = []

        for i in range(6):
            samples.append(adc_reader.take_reading()[reference_channel])

        assert (
            0.02 < mean(samples) < 0.256
        ), f"Recorded {mean(samples):0.3f} in REF, should ideally be between 0.02 and 0.256. Current IR LED: {ir_intensity}%."

        # also check for stability: the std. of the reference should be quite low:
        assert variance(samples) < 1e-2, f"Too much noise in REF channel, observed {variance(samples)}."


def test_PD_is_near_0_volts_for_blank(
    client: Client, logger: CustomLogger, unit: str, experiment: str
) -> None:
    assert is_HAT_present(), "HAT is not detected."
    reference_channel = cast(PdChannel, config.get("od_config.photodiode_channel_reverse", REF_keyword))

    if reference_channel == "1":
        signal_channel = cast(PdChannel, "2")
    else:
        signal_channel = cast(PdChannel, "1")

    angle = config.get("od_config.photodiode_channel", signal_channel, fallback=None)

    assert angle in ["90", "45", "135"], f"Angle {angle} not valid for this test."

    signals = []

    with start_od_reading(
        od_angle_channel1=angle if signal_channel == "1" else None,  # don't use REF
        od_angle_channel2=angle if signal_channel == "2" else None,  # don't use REF
        interval=1.15,
        unit=unit,
        fake_data=is_testing_env(),
        experiment=experiment,
        use_calibration=False,
    ) as od_stream:
        for i, reading in enumerate(od_stream, start=1):
            signals.append(reading.ods[signal_channel].od)

            if i == 6:
                break

    mean_signal = mean(signals)

    THRESHOLD = 0.035
    assert mean_signal <= THRESHOLD, f"Blank signal too high: {mean_signal=} > {THRESHOLD}"


def test_detect_heating_pcb(client: Client, logger: CustomLogger, unit: str, experiment: str) -> None:
    assert is_heating_pcb_present(), "Heater PCB is not connected, or i2c is not working."


def test_positive_correlation_between_temperature_and_heating(
    client, logger: CustomLogger, unit: str, experiment: str
) -> None:
    assert is_heating_pcb_present(), "Heater PCB is not connected, or i2c is not working."

    measured_pcb_temps = []
    dcs = list(range(0, 30, 3))

    with TemperatureController(unit, experiment, "only_record_temperature") as tc:
        logger.debug("Varying heating.")
        for dc in dcs:
            tc._update_heater(dc)
            sleep(1.5)
            measured_pcb_temps.append(tc.read_external_temperature())

        tc._update_heater(0)
        measured_correlation = round(correlation(dcs, measured_pcb_temps), 2)
        logger.debug(f"Correlation between temp sensor and heating: {measured_correlation}")
        assert (
            measured_correlation > 0.9
        ), f"Temp and DC% correlation was not high enough {dcs=}, {measured_pcb_temps=}"


def test_aux_power_is_not_too_high(client: Client, logger: CustomLogger, unit: str, experiment: str) -> None:
    assert is_HAT_present(), "HAT was not detected."
    assert voltage_in_aux() <= 18.0, f"Voltage measured {voltage_in_aux()} > 18.0V"


def test_positive_correlation_between_rpm_and_stirring(
    client, logger: CustomLogger, unit: str, experiment: str
) -> None:
    assert is_HAT_present(), "HAT was not detected."
    assert is_heating_pcb_present(), "Heating PCB was not detected."
    assert voltage_in_aux() <= 18.0, f"Voltage measured {voltage_in_aux()} > 18.0V"

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
        target_rpm=0, unit=unit, experiment=experiment, rpm_calculator=None
    ) as st, stirring.RpmFromFrequency() as rpm_calc:
        rpm_calc.setup()
        st.duty_cycle = initial_dc
        st.start_stirring()
        sleep(0.75)

        for i in range(n_samples):
            p = i / n_samples
            dc = start * (1 - p) + p * end

            st.set_duty_cycle(dc)
            sleep(0.75)
            measured_rpms.append(rpm_calc.estimate(3.0))
            dcs.append(dc)

        measured_correlation = round(correlation(dcs, measured_rpms), 2)
        logger.debug(f"Correlation between stirring RPM and duty cycle: {measured_correlation}")
        logger.debug(f"{dcs=}, {measured_rpms=}")
        assert measured_correlation > 0.9, f"RPM correlation not high enough: {(dcs, measured_rpms)}"


class BatchTestRunner:
    def __init__(self, tests_to_run: list[Callable], *test_func_args, experiment: str) -> None:
        self.count_tested = 0
        self.count_passed = 0
        self.tests_to_run = tests_to_run
        self.experiment = experiment
        self._thread = Thread(target=self._run, args=test_func_args)  # don't make me daemon: 295

    def start(self):
        self._thread.start()
        return self

    def collect(self) -> SummableDict:
        self._thread.join()
        return SummableDict({"count_tested": self.count_tested, "count_passed": self.count_passed})

    def _run(self, client, logger: CustomLogger, unit: str, testing_experiment: str) -> None:
        for test in self.tests_to_run:
            res = False
            test_name = test.__name__

            try:
                test(client, logger, unit, testing_experiment)
                res = True
            except Exception as e:
                logger.debug(e, exc_info=True)
                logger.warning(f"{test_name.replace('_', ' ')}: {e}")

            logger.debug(f"{test_name}: {'✅' if res else '❌'}")

            self.count_tested += 1
            self.count_passed += int(res)

            client.publish(
                f"pioreactor/{unit}/{self.experiment}/self_test/{test_name}",
                int(res),
                retain=True,
            )

            with local_persistant_storage("self_test_results") as c:
                c[(self.experiment, test_name)] = int(res)


def get_failed_test_names(experiment: str) -> Iterator[str]:
    with local_persistant_storage("self_test_results") as c:
        for name in get_all_test_names():
            if c.get((experiment, name)) == 0:
                yield name


def get_all_test_names() -> Iterator[str]:
    return (name for name in vars(sys.modules[__name__]).keys() if name.startswith("test_"))


@click.command(name="self_test")
@click.option("-k", help="see pytest's -k argument", type=str)
@click.option("--retry-failed", is_flag=True, help="retry only previous failed tests", type=str)
def click_self_test(k: Optional[str], retry_failed: bool) -> int:
    """
    Test the input/output in the Pioreactor
    """
    unit = get_unit_name()
    testing_experiment = get_testing_experiment_name()
    experiment = get_assigned_experiment_name(unit)
    logger = create_logger("self_test", unit=unit, experiment=experiment)

    A_TESTS = (
        test_pioreactor_HAT_present,
        test_detect_heating_pcb,
        test_positive_correlation_between_temperature_and_heating,
        test_aux_power_is_not_too_high,
    )
    B_TESTS = (
        test_all_positive_correlations_between_pds_and_leds,
        test_ambient_light_interference,
        test_REF_is_lower_than_0_dot_256_volts,
        test_REF_is_in_correct_position,
        test_PD_is_near_0_volts_for_blank,
        test_positive_correlation_between_rpm_and_stirring,
    )

    with managed_lifecycle(unit, experiment, "self_test") as state:
        client = state.mqtt_client
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
        tests_to_run: Iterator[str]
        if retry_failed:
            tests_to_run = get_failed_test_names(experiment)
        else:
            tests_to_run = get_all_test_names()

        if k:
            tests_to_run = (name for name in tests_to_run if k in name)

        functions_to_test = {vars(sys.modules[__name__])[name] for name in tuple(tests_to_run)}

        logger.info(f"Starting self-test. Running {len(functions_to_test)} tests.")

        # and clear the mqtt cache first
        for f in functions_to_test:
            client.publish(
                f"pioreactor/{unit}/{experiment}/self_test/{f.__name__}",
                None,
                retain=True,
            )

        # some tests can be run in parallel.
        test_args = (client, logger, unit, testing_experiment)
        RunnerA = BatchTestRunner(
            [f for f in A_TESTS if f in functions_to_test], *test_args, experiment=experiment
        ).start()
        RunnerB = BatchTestRunner(
            [f for f in B_TESTS if f in functions_to_test], *test_args, experiment=experiment
        ).start()

        results = RunnerA.collect() + RunnerB.collect()
        count_tested, count_passed = results["count_tested"], results["count_passed"]
        count_failures = int(count_tested - count_passed)

        client.publish(
            f"pioreactor/{unit}/{experiment}/self_test/all_tests_passed",
            int(count_failures == 0),
            retain=True,
        )

        if count_tested == 0:
            logger.info("No tests ran 🟡")
        elif count_failures == 0:
            logger.info("All tests passed ✅")
        elif count_failures > 0:
            logger.info(f"{count_failures} failed test{'s' if count_failures > 1 else ''} ❌")

        # clear my retained messages
        prune_retained_messages(f"pioreactor/{unit}/{testing_experiment}/#")

        return int(count_failures > 0)
