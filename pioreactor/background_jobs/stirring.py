# -*- coding: utf-8 -*-

from time import sleep, perf_counter
from typing import Optional
import json
import click


from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.hardware_mappings import PWM_TO_PIN, HALL_SENSOR_PIN
from pioreactor.utils.pwm import PWM
from pioreactor.utils import clamp, local_persistant_storage
from pioreactor.utils.gpio_helpers import GPIO_states, set_gpio_availability
from pioreactor.utils.streaming_calculations import PID
from pioreactor.utils.timing import RepeatedTimer


class RpmCalculator:
    """
    Super class for determining how to calculate the RPM from the hall sensor.


    We do some funky things with RPi.GPIO here.

    1) to minimize global imports, we import in init, and attach the module to self.
    2) More egregious: we previously has this class call `add_event_detect` and afterwards `remove_event_detect`
       in each __call__ - this made sure that we were saving CPU resources when we were not measuring the RPM.
       This was causing `Bus error`, and crashing Python. What I think was happening was that the folder
       `/sys/class/gpio/gpio15` was constantly being written and deleted in each __call__, causing problems with the
       SD card. Anyways, what we do now is turn the pin from IN to OUT inbetween the calls to RPM measurement. This
       is taken care of in `turn_{on,off}_collection`. Flipping this only writes to `/sys/class/gpio/gpio15/direction`.

    """

    hall_sensor_pin = HALL_SENSOR_PIN

    def __init__(self):
        set_gpio_availability(self.hall_sensor_pin, GPIO_states.GPIO_UNAVAILABLE)

        import RPi.GPIO as GPIO

        self.GPIO = GPIO
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setup(self.hall_sensor_pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)
        self.GPIO.add_event_detect(
            self.hall_sensor_pin, self.GPIO.RISING, callback=self.callback, bouncetime=2
        )
        self.turn_off_collection()

    def turn_off_collection(self):
        self.GPIO.setup(self.hall_sensor_pin, self.GPIO.OUT)

    def turn_on_collection(self):
        self.GPIO.setup(self.hall_sensor_pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)

    def cleanup(self):
        self.GPIO.cleanup(self.hall_sensor_pin)
        set_gpio_availability(self.hall_sensor_pin, GPIO_states.GPIO_AVAILABLE)

    def __call__(self, seconds_to_observe: float) -> Optional[int]:
        pass


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

    def callback(self, *args):
        self._rpm_counter = self._rpm_counter + 1

    def __call__(self, seconds_to_observe: float) -> int:

        self._rpm_counter = 0

        self.turn_on_collection()
        sleep(seconds_to_observe)
        self.turn_off_collection()

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
    duty_cycle: float = config.getint(
        "stirring", "initial_duty_cycle", fallback=60.0
    )  # only used in calibration isn't defined.
    actual_rpm: float = 0

    def __init__(
        self,
        target_rpm: int,
        unit: str,
        experiment: str,
        rpm_calculator: Optional[RpmCalculator],
        hertz=67,
    ):
        super(Stirrer, self).__init__(
            job_name="stirring", unit=unit, experiment=experiment
        )
        self.logger.debug(f"Starting stirring with initial {target_rpm} RPM.")
        self.pwm_pin = PWM_TO_PIN[config.getint("PWM_reverse", "stirring")]

        self.pwm = PWM(self.pwm_pin, hertz)
        self.pwm.lock()

        self.rpm_calculator = rpm_calculator
        self.rpm_to_dc_lookup = self.initialize_rpm_to_dc_lookup()
        self.target_rpm = target_rpm

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
        )

        # set up thread to periodically check the rpm
        self.rpm_check_repeated_thread = RepeatedTimer(
            19,
            self.poll_and_update_dc,
            job_name=self.job_name,
            run_immediately=True,
            poll_for_seconds=4,
        )

    def initialize_rpm_to_dc_lookup(self):
        with local_persistant_storage("stirring_calibration") as cache:
            if "linear_v1" in cache:
                parameters = json.loads(cache["linear_v1"])
                coef = parameters.pop("rpm_coef")
                intercept = parameters.pop("intercept")
                # we scale this by 90% to make sure the PID + prediction doesn't overshoot,
                # better to be conservative here.
                # equilivant to a weighted average: 0.1 * current + 0.9 * predicted
                return lambda rpm: self.duty_cycle - 0.9 * (
                    self.duty_cycle - (coef * rpm + intercept)
                )
            else:
                return lambda rpm: self.duty_cycle

    def on_disconnect(self):

        self.rpm_check_repeated_thread.cancel()
        self.stop_stirring()
        self.pwm.cleanup()

        if self.rpm_calculator:
            self.rpm_calculator.cleanup()

        self.clear_mqtt_cache()

    def start_stirring(self):
        self.pwm.start(100)  # get momentum to start
        sleep(0.25)
        self.set_duty_cycle(self.duty_cycle)
        sleep(0.75)

        try:
            self.rpm_check_repeated_thread.start()
        except RuntimeError:
            # possibly the thread has already started
            pass

    def poll(self, poll_for_seconds: float) -> Optional[int]:
        """
        Returns an RPM, or None if not measuring RPM.
        """
        if self.rpm_calculator:
            measured_rpm = self.rpm_calculator(poll_for_seconds)
            if self.actual_rpm:
                # use a simple EMA, 0.05 chosen arbitrarily
                self.actual_rpm = 0.05 * self.actual_rpm + 0.95 * measured_rpm
            else:
                self.actual_rpm = measured_rpm
        else:
            self.actual_rpm = None

        if self.actual_rpm == 0:
            self.logger.warning("Stirring RPM is 0 - has it failed?")

        return self.actual_rpm

    def poll_and_update_dc(self, poll_for_seconds: float):
        measured_rpm = self.poll(poll_for_seconds)

        if measured_rpm is None:
            return

        result = self.pid.update(measured_rpm, dt=1)
        self.set_duty_cycle(self.duty_cycle + result)

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
        self.set_duty_cycle(self.rpm_to_dc_lookup(self.target_rpm))
        self.pid.set_setpoint(self.target_rpm)


def start_stirring(target_rpm=0, unit=None, experiment=None, ignore_rpm=False) -> Stirrer:
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
    default=config.getint("stirring", "target_rpm", fallback=0),
    help="set the target RPM",
    show_default=True,
    type=click.IntRange(0, 1000, clamp=True),
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
