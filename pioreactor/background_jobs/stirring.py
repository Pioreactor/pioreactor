# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from contextlib import suppress
from time import perf_counter
from time import sleep
from typing import Callable
from typing import Optional

import click

from pioreactor import error_codes
from pioreactor import exc
from pioreactor import hardware
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.config import config
from pioreactor.utils import clamp
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.gpio_helpers import GPIO_states
from pioreactor.utils.gpio_helpers import set_gpio_availability
from pioreactor.utils.pwm import PWM
from pioreactor.utils.streaming_calculations import PID
from pioreactor.utils.timing import current_utc_time
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name


class RpmCalculator:
    """
    Super class for determining how to calculate the RPM from the hall sensor.

    We do some funky things with RPi.GPIO here.

    1) to minimize global imports, we import in init, and attach the module to self.
    2) More egregious: we previously had this class call `add_event_detect` and afterwards `remove_event_detect`
       in each __call__ - this made sure that we were saving CPU resources when we were not measuring the RPM.
       This was causing `Bus error`, and crashing Python. What I think was happening was that the folder
       `/sys/class/gpio/gpio25` was constantly being written and deleted in each __call__, causing problems with the
       SD card. Anyways, what we do now is turn the pin from IN to OUT inbetween the calls to RPM measurement. This
       is taken care of in `turn_{on,off}_collection`. Flipping this only writes to `/sys/class/gpio/gpio15/direction` once.

    """

    hall_sensor_pin = hardware.HALL_SENSOR_PIN

    def __init__(self) -> None:
        set_gpio_availability(self.hall_sensor_pin, GPIO_states.GPIO_UNAVAILABLE)

        import RPi.GPIO as GPIO  # type: ignore

        self.GPIO = GPIO
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setup(self.hall_sensor_pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)

        # ignore any changes that occur within 15ms - at 1000rpm (very fast), the
        # delta between changes is ~60ms, so 15ms is good enough.
        self.GPIO.add_event_detect(
            self.hall_sensor_pin, self.GPIO.RISING, callback=self.callback, bouncetime=15
        )
        self.turn_off_collection()

    def turn_off_collection(self) -> None:
        self.GPIO.setup(self.hall_sensor_pin, self.GPIO.OUT)

    def turn_on_collection(self) -> None:
        self.GPIO.setup(self.hall_sensor_pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)

    def cleanup(self) -> None:
        self.GPIO.cleanup(self.hall_sensor_pin)
        set_gpio_availability(self.hall_sensor_pin, GPIO_states.GPIO_AVAILABLE)

    def __call__(self, seconds_to_observe: float) -> float:
        return 0.0

    def callback(self, *args) -> None:
        pass

    def sleep_for(self, seconds) -> None:
        sleep(seconds)

    def __enter__(self) -> RpmCalculator:
        return self

    def __exit__(self, *args) -> None:
        self.cleanup()


class RpmFromFrequency(RpmCalculator):
    """
    Averages the duration between rises in an N second window. This is more accurate (but less robust)
    than RpmFromCount
    """

    _running_sum = 0
    _running_count = 0
    _start_time = None
    _is_first_delta = True

    def callback(self, *args) -> None:
        obs_time = perf_counter()

        if self._start_time is not None:
            if not self._is_first_delta:
                self._running_sum += obs_time - self._start_time
                self._running_count += 1
            else:
                self._is_first_delta = False

        self._start_time = obs_time

    def clear_aggregates(self) -> None:
        self._running_sum = 0
        self._running_count = 0
        self._start_time = None
        self._is_first_delta = True

    def __call__(self, seconds_to_observe: float) -> float:

        self.clear_aggregates()
        self.turn_on_collection()
        self.sleep_for(seconds_to_observe)
        self.turn_off_collection()

        if self._running_sum == 0:
            return 0
        else:
            # we should be able to detect if we are missing pings, as they would be a near integer
            # of the average of "okay" values.
            #    measured Δ time vs index
            #    |
            #  Δ |
            #    |      x      x
            #    |xxxxxxxxxxxxxxxxxxxx
            #     --------------------|
            #           index
            #
            # however, we need the array, but we only record the running counts/sums
            # solution: running max and running min.
            # False positives are when the duty cycle significantly changes however...

            # if self._running_max > 1.75 * self._running_min:
            #     self.logger.debug(
            #         f"RpmCalculator is possible skipping some signal: {self._running_max=}, {self._running_min=}."
            #     )

            return self._running_count * 60 / self._running_sum


class RpmFromCount(RpmCalculator):
    """
    Counts the number of rises in an N second window.
    """

    _rpm_counter = 0

    def callback(self, *args) -> None:
        self._rpm_counter = self._rpm_counter + 1

    def __call__(self, seconds_to_observe: float) -> float:

        self._rpm_counter = 0

        self.turn_on_collection()
        self.sleep_for(seconds_to_observe)
        self.turn_off_collection()

        return self._rpm_counter * 60 / seconds_to_observe


class Stirrer(BackgroundJob):
    """
    Parameters
    ------------

    target_rpm: float
        Send message to "pioreactor/{unit}/{experiment}/stirring/target_rpm/set" to change the stirring speed.
    rpm_calculator: RpmCalculator
        See RpmCalculator and examples below.

    Notes
    -------

    The create a feedback loop between the duty-cycle level and the RPM, we set up a polling algorithm. We set up
    an edge detector on the hall sensor pin, and count the number of pulses in N seconds. We convert this count to RPM, and
    then use a PID system to update the amount of duty cycle to apply.

    We perform the above every N seconds. That is, there is PID controller that checks every N seconds and nudges the duty cycle
    to match the requested RPM.


    Examples
    ---------

    > st = Stirrer(500, unit, experiment)
    > st.start_stirring()
    """

    published_settings = {
        "target_rpm": {"datatype": "json", "settable": True, "unit": "RPM"},
        "measured_rpm": {"datatype": "json", "settable": False, "unit": "RPM"},
        "duty_cycle": {"datatype": "float", "settable": True, "unit": "%"},
    }
    _previous_duty_cycle: float = 0
    duty_cycle: float = config.getfloat(
        "stirring", "initial_duty_cycle"
    )  # only used if calibration isn't defined.
    _measured_rpm: Optional[float] = None

    def __init__(
        self,
        target_rpm: float,
        unit: str,
        experiment: str,
        rpm_calculator: Optional[RpmCalculator],
        hertz: float = 150,
    ) -> None:
        super(Stirrer, self).__init__(
            job_name="stirring", unit=unit, experiment=experiment
        )
        self.logger.debug(f"Starting stirring with initial {target_rpm} RPM.")
        self.rpm_calculator = rpm_calculator

        if not hardware.is_HAT_present():
            self.logger.error("Pioreactor HAT must be present.")
            self.set_state(self.DISCONNECTED)
            raise exc.HardwareNotFoundError("Pioreactor HAT must be present.")

        if (self.rpm_calculator is not None) and not hardware.is_heating_pcb_present():
            self.logger.error("Heating PCB must be present to measure RPM.")
            self.set_state(self.DISCONNECTED)
            raise exc.HardwareNotFoundError("Heating PCB must be present to measure RPM.")

        pin = hardware.PWM_TO_PIN[config.get("PWM_reverse", "stirring")]
        self.pwm = PWM(pin, hertz, unit=unit, experiment=experiment)
        self.pwm.lock()

        self.target_rpm = target_rpm
        self.rpm_to_dc_lookup = self.initialize_rpm_to_dc_lookup(self.target_rpm)
        self.duty_cycle = self.rpm_to_dc_lookup(self.target_rpm)

        # set up PID
        self.pid = PID(
            Kp=config.getfloat("stirring.pid", "Kp"),
            Ki=config.getfloat("stirring.pid", "Ki"),
            Kd=config.getfloat("stirring.pid", "Kd"),
            setpoint=self.target_rpm,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="rpm",
            output_limits=(-20, 20),  # avoid whiplashing
        )

        # set up thread to periodically check the rpm
        self.rpm_check_repeated_thread = RepeatedTimer(
            91,
            self.poll_and_update_dc,
            job_name=self.job_name,
            run_immediately=True,
            run_after=5,
            poll_for_seconds=4,  # technically should be a function of the RPM: lower RPM, longer to get sufficient data.
        )

    def initialize_rpm_to_dc_lookup(self, target_rpm: float) -> Callable:
        if self.rpm_calculator is None:
            # if we can't track RPM, no point in adjusting DC, use what is in config.ini
            return lambda rpm: self.duty_cycle

        with local_persistant_storage("stirring_calibration") as cache:

            if "linear_v1" in cache:
                parameters = json.loads(cache["linear_v1"])
                coef = parameters["rpm_coef"]
                intercept = parameters["intercept"]

                # since we have calibration data, and the initial_duty_cycle could be
                # far off, giving the below equation a bad "first step". We set it here.
                self.duty_cycle = coef * target_rpm + intercept

                # we scale this by 90% to make sure the PID + prediction doesn't overshoot,
                # better to be conservative here.
                # equivalent to a weighted average: 0.1 * current + 0.9 * predicted
                return lambda rpm: self.duty_cycle - 0.90 * (
                    self.duty_cycle - (coef * rpm + intercept)
                )
            else:
                return lambda rpm: self.duty_cycle

    def on_disconnected(self) -> None:

        with suppress(AttributeError):
            self.rpm_check_repeated_thread.cancel()

        with suppress(AttributeError):
            self.stop_stirring()
            self.pwm.cleanup()

        with suppress(AttributeError):
            if self.rpm_calculator:
                self.rpm_calculator.cleanup()

    def start_stirring(self) -> None:
        self.pwm.start(100)  # get momentum to start
        sleep(0.10)
        self.set_duty_cycle(self.duty_cycle)
        sleep(0.75)
        self.rpm_check_repeated_thread.start()  # .start is idempotent

    def poll(self, poll_for_seconds: float) -> Optional[float]:
        """
        Returns an RPM, or None if not measuring RPM.
        """
        if self.rpm_calculator is None:
            return None

        recent_rpm = self.rpm_calculator(poll_for_seconds)
        if recent_rpm == 0:
            # TODO: attempt to restart stirring
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/monitor/flicker_led_with_error_code",
                error_codes.STIRRING_FAILED_ERROR_CODE,
            )
            self.logger.warning("Stirring RPM is 0 - has it failed?")

        if self._measured_rpm is not None:
            # use a simple EMA, alpha chosen arbitrarily, but should be a function of delta time.
            self._measured_rpm = 0.025 * self._measured_rpm + 0.975 * recent_rpm
        else:
            self._measured_rpm = recent_rpm

        self.measured_rpm = {"timestamp": current_utc_time(), "rpm": self._measured_rpm}
        return self._measured_rpm

    def poll_and_update_dc(self, poll_for_seconds: float) -> None:
        self.poll(poll_for_seconds)

        if self._measured_rpm is None:
            return

        result = self.pid.update(self._measured_rpm)
        self.set_duty_cycle(self.duty_cycle + result)

    def stop_stirring(self) -> None:
        # if the user unpauses, we want to go back to their previous value, and not the default.
        self.set_duty_cycle(0)

    def on_ready_to_sleeping(self) -> None:
        self.rpm_check_repeated_thread.pause()
        self.stop_stirring()

    def on_sleeping_to_ready(self) -> None:
        self.duty_cycle = self._previous_duty_cycle
        self.rpm_check_repeated_thread.unpause()
        self.start_stirring()

    def set_duty_cycle(self, value: float) -> None:
        self._previous_duty_cycle = self.duty_cycle
        self.duty_cycle = clamp(0, round(float(value), 5), 100)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def set_target_rpm(self, value: float) -> None:
        self.target_rpm = float(value)
        self.set_duty_cycle(self.rpm_to_dc_lookup(self.target_rpm))
        self.pid.set_setpoint(self.target_rpm)

    def block_until_rpm_is_close_to_target(self, abs_tolerance: float = 15) -> None:
        """
        This function blocks until the stirring is "close enough" to the target RPM.

        """
        if self.rpm_calculator is None:
            # can't block if we aren't recording the RPM
            return

        while (self._measured_rpm is not None) and abs(
            self._measured_rpm - self.target_rpm
        ) > abs_tolerance:
            sleep(0.25)


def start_stirring(
    target_rpm: float = 0.0,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    ignore_rpm=False,
) -> Stirrer:
    unit = unit or get_unit_name()
    experiment = experiment or get_latest_experiment_name()

    if ignore_rpm:
        rpm_calculator = None
    else:
        rpm_calculator = RpmFromFrequency()

    stirrer = Stirrer(
        target_rpm=target_rpm,
        unit=unit,
        experiment=experiment,
        rpm_calculator=rpm_calculator,
    )
    stirrer.start_stirring()
    return stirrer


@click.command(name="stirring")
@click.option(
    "--target-rpm",
    default=config.getfloat("stirring", "target_rpm", fallback=0),
    help="set the target RPM",
    show_default=True,
    type=click.FloatRange(0, 1200, clamp=True),
)
@click.option(
    "--ignore-rpm",
    help="don't use feedback loop",
    is_flag=True,
)
def click_stirring(target_rpm, ignore_rpm):
    """
    Start the stirring of the Pioreactor.
    """
    st = start_stirring(target_rpm=target_rpm, ignore_rpm=ignore_rpm)
    st.block_until_disconnected()
