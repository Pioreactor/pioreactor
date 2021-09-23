# -*- coding: utf-8 -*-

from signal import pause
from time import sleep, perf_counter
from typing import Optional
import click

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.hardware_mappings import PWM_TO_PIN, HALL_SENSOR_PIN
from pioreactor.utils.pwm import PWM
from pioreactor.utils import clamp
from pioreactor.utils.gpio_helpers import GPIO_states, set_gpio_availability
from pioreactor.utils.streaming_calculations import PID
from pioreactor.utils.timing import RepeatedTimer


class RpmCalculator:
    """
    Super class for determining how to calculate the RPM from the hall sensor.
    """

    hall_sensor_pin = HALL_SENSOR_PIN

    def __init__(self):
        set_gpio_availability(self.hall_sensor_pin, GPIO_states.GPIO_UNAVAILABLE)

        import RPi.GPIO as GPIO

        self.GPIO = GPIO
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setup(
            self.hall_sensor_pin, self.GPIO.OUT, pull_up_down=self.GPIO.PUD_UP
        )  # we will turn on later.
        self.GPIO.add_event_detect(
            self.hall_sensor_pin, self.GPIO.RISING, callback=self.callback, bouncetime=2
        )

    def turn_off_collection(self):
        self.GPIO.setup(self.hall_sensor_pin, self.GPIO.OUT)

    def turn_on_collection(self):
        self.GPIO.setup(self.hall_sensor_pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)

    def cleanup(self):
        self.GPIO.remove_event_detect(self.hall_sensor_pin)
        self.GPIO.cleanup(self.hall_sensor_pin)
        set_gpio_availability(self.hall_sensor_pin, GPIO_states.GPIO_AVAILABLE)

    def __call__(self, seconds_to_observe: float) -> Optional[int]:
        pass


class EmptyRpmCalculator(RpmCalculator):
    def __call__(self, seconds_to_observe: float) -> None:
        return None


class RpmFromFrequency(RpmCalculator):
    """
    Averages the duration between rises in an N second window. This is more accurate (but less robust)
    than RpmFromCount
    """

    _running_sum = 0
    _running_count = 0
    _start_time = None

    def callback(self, *args):
        obs_time = perf_counter()

        if self._start_time is not None:
            self._running_sum += obs_time - self._start_time
            self._running_count += 1

        self._start_time = obs_time

    def __call__(self, seconds_to_observe: float) -> int:

        self._running_sum = 0
        self._running_count = 0
        self._start_time = None

        self.turn_on_collection()
        sleep(seconds_to_observe)
        self.turn_off_collection()

        if self._running_sum == 0:
            return 0
        else:
            return round(self._running_count * 60 / self._running_sum)


class RpmFromCount(RpmCalculator):
    """
    Counts the number of rises in an N second window.
    """

    _rpm_counter = 0

    def _callback(self, *args):
        self._rpm_counter = self._rpm_counter + 1

    def __call__(self, seconds_to_observe: float) -> int:

        self._rpm_counter = 0

        self.collect = True
        sleep(seconds_to_observe)
        self.collect = False

        return round(self._rpm_counter * 60 / seconds_to_observe)


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
        "target_rpm": {"datatype": "int", "settable": True, "unit": "RPM"},
        "actual_rpm": {"datatype": "int", "settable": False, "unit": "RPM"},
    }
    _previous_duty_cycle: float = 0
    rpm_check_thread = None

    def __init__(
        self,
        target_rpm: int,
        unit: str,
        experiment: str,
        rpm_calculator: RpmCalculator,
        hertz=67,
        initial_duty_cycle: float = 60,  # initial duty cycle, we will deviate from this in the feedback loop immediately.
    ):
        super(Stirrer, self).__init__(
            job_name="stirring", unit=unit, experiment=experiment
        )
        self.logger.debug(f"Starting stirring with initial {target_rpm} RPM.")
        self.pwm_pin = PWM_TO_PIN[config.getint("PWM_reverse", "stirring")]

        self.pwm = PWM(self.pwm_pin, hertz)
        self.pwm.lock()

        self.duty_cycle = initial_duty_cycle

        self.rpm_calculator = rpm_calculator

        # set up PID
        self.target_rpm = target_rpm
        self.pid = PID(
            Kp=config.getfloat("stirring.pid", "Kp"),
            Ki=config.getfloat("stirring.pid", "Ki"),
            Kd=config.getfloat("stirring.pid", "Kd"),
            setpoint=self.target_rpm,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="rpm",
        )

        # set up thread to periodically check the rpm
        self.rpm_check_repeated_thread = RepeatedTimer(
            10,
            self.poll_and_update_dc,
            job_name=self.job_name,
            run_immediately=True,
            poll_for_seconds=4,
        )

    def on_disconnect(self):

        self.rpm_check_repeated_thread.cancel()
        self.stop_stirring()
        self.pwm.cleanup()
        self.rpm_calculator.cleanup()
        self.clear_mqtt_cache()

    def start_stirring(self):
        self.pwm.start(100)  # get momentum to start
        sleep(0.5)
        self.set_duty_cycle(self.duty_cycle)
        sleep(0.25)

        try:
            self.rpm_check_repeated_thread.start()
        except RuntimeError:
            # possibly the thread has already started
            pass

    def poll(self, poll_for_seconds: float) -> Optional[int]:
        """
        Returns an RPM, or None if not measure RPM.
        """
        self.actual_rpm = self.rpm_calculator(poll_for_seconds)
        if self.actual_rpm == 0:
            self.logger.warning("Stirring RPM is 0 - has it failed?")

        return self.actual_rpm

    def poll_and_update_dc(self, poll_for_seconds: float):
        measured_rpm = self.poll(poll_for_seconds)

        if measured_rpm is None:
            return

        result = self.pid.update(measured_rpm, dt=1)
        self.set_duty_cycle(self.duty_cycle + result)
        self.logger.debug(f"duty_cycle={self.duty_cycle}")

    def stop_stirring(self):
        # if the user unpauses, we want to go back to their previous value, and not the default.
        self.set_duty_cycle(0)

    def on_ready_to_sleeping(self):
        self._previous_duty_cycle = self.duty_cycle
        self.rpm_check_repeated_thread.pause()
        self.stop_stirring()

    def on_sleeping_to_ready(self):
        self.duty_cycle = self._previous_duty_cycle
        self.rpm_check_repeated_thread.unpause()
        self.start_stirring()

    def set_duty_cycle(self, value):
        self.duty_cycle = clamp(0, round(float(value), 5), 100)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def set_target_rpm(self, value):
        self.target_rpm = float(value)
        self.pid.set_setpoint(self.target_rpm)


def start_stirring(
    target_rpm=0, unit=None, experiment=None, initial_duty_cycle=60
) -> Stirrer:
    unit = unit or get_unit_name()
    experiment = experiment or get_latest_experiment_name()

    stirrer = Stirrer(
        target_rpm=target_rpm,
        unit=unit,
        experiment=experiment,
        rpm_calculator=RpmFromFrequency(),
        initial_duty_cycle=initial_duty_cycle,
    )
    stirrer.start_stirring()
    return stirrer


@click.command(name="stirring")
@click.option(
    "--target-rpm",
    default=config.getint("stirring", "target_rpm", fallback=0),
    help="set the target RPM",
    show_default=True,
    type=click.IntRange(0, 1000, clamp=True),
)
@click.option(
    "--initial-duty-cycle",
    default=config.getint("stirring", "initial_duty_cycle", fallback=60),
    help="set the initial duty cycle",
    show_default=True,
    type=click.IntRange(0, 100, clamp=True),
)
def click_stirring(target_rpm, initial_duty_cycle):
    """
    Start the stirring of the Pioreactor.
    """
    start_stirring(target_rpm=target_rpm, initial_duty_cycle=initial_duty_cycle)
    pause()
