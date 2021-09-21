# -*- coding: utf-8 -*-

import time, signal

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


class Stirrer(BackgroundJob):
    """
    Parameters
    ------------

    duty_cycle: int
        Send message to "pioreactor/{unit}/{experiment}/stirring/duty_cycle/set" to change the stirring speed.


    Notes
    -------

    The create a feedback loop between the duty-cycle level and the RPM, we set up a polling algorithm. We set up
    an edge detector on the hall sensor pin, and count the number of pulses in N seconds. We convert this count to RPM, and
    then use a PID system to update the amount of duty cycle to apply.

    We perform the above in three places:
    1. When the job starts or unpauses, we tune the DC (using above algorithm) until we reach a value "close" to the `target_rpm`
    2. When we change the `target_rpm`, we tune the DC until we reach a value "close" to the `target_rpm`
    3. Every N minutes, we perform a small tweak to correct for long term changes.

    Note that we _don't_ measure the time between pulses (i.e. measure the frequency) because the stirring could be stalled,
    and we would have an never-returning trigger.


    Examples
    ---------

    > st = Stirrer(500, unit, experiment)
    > st.start_stirring()


     - [ ] implement some checks for failed stirring / motor / fan
     - [ ] test pausing
     - [ ] what happens if I change target_rpm in quick succession?

    """

    published_settings = {
        "target_rpm": {"datatype": "float", "settable": True, "unit": "RPM"},
        "actual_rpm": {"datatype": "float", "settable": False, "unit": "RPM"},
    }
    _previous_duty_cycle = None
    hall_sensor_pin = HALL_SENSOR_PIN
    _rpm_counter: int = 0
    duty_cycle: float = 50  # initial duty cycle, we will deviate from this in the feedback loop immediately.

    def __init__(
        self,
        target_rpm,
        unit,
        experiment,
        hertz=67,
    ):
        super(Stirrer, self).__init__(
            job_name="stirring", unit=unit, experiment=experiment
        )
        self.logger.debug(f"Starting stirring with initial {target_rpm} RPM.")
        self.pwm_pin = PWM_TO_PIN[config.getint("PWM_reverse", "stirring")]

        set_gpio_availability(self.pwm_pin, GPIO_states.GPIO_UNAVAILABLE)
        set_gpio_availability(self.hall_sensor_pin, GPIO_states.GPIO_UNAVAILABLE)

        self.pwm = PWM(self.pwm_pin, hertz)
        self.pwm.lock()

        # set up PID
        self.target_rpm = target_rpm
        self.pid = PID(
            Kp=config.getfloat("stirring.pid", "Kp"),
            Ki=0.0,
            Kd=0.0,
            setpoint=self.target_rpm,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="rpm",
        )

        # set up thread to periodically check the rpm
        self.rpm_check_thread = RepeatedTimer(
            120,
            self.poll_and_update_dc,
            job_name=self.job_name,
            run_immediately=False,
            poll_for_seconds=6,
        ).start()

    def on_disconnect(self):

        self.stop_stirring()
        self.pwm.cleanup()
        self.rpm_check_thread.cancel()
        self.clear_mqtt_cache()

        set_gpio_availability(self.pwm_pin, GPIO_states.GPIO_AVAILABLE)
        set_gpio_availability(self.hall_sensor_pin, GPIO_states.GPIO_AVAILABLE)

    def start_stirring(self):
        # stop the thread from running,
        self.rpm_check_thread.pause()

        self.pwm.start(100)  # get momentum to start
        time.sleep(0.5)
        self.set_duty_cycle(self.duty_cycle)
        time.sleep(0.5)

        # we need to start the feedback loop here to orient close to our desired value
        while True:
            error = self.poll_and_update_dc(4)
            if (
                abs(error) < 0.15
            ):  # TODO: I don't like this check, it will tend to overshoot.
                break
            time.sleep(0.1)

        self.rpm_check_thread.unpause()

    def poll_and_update_dc(self, poll_for_seconds: float):

        count = self._count_rotations(poll_for_seconds)
        self.actual_rpm = count * 60 / poll_for_seconds
        self.logger.debug(f"count={count}")

        result = self.pid.update(self.actual_rpm, dt=1)
        self.set_duty_cycle(self.duty_cycle + result)
        self.logger.debug(f"duty_cycle={self.duty_cycle}")

        return result

    def _count_rotations(self, seconds: float):
        import RPi.GPIO as GPIO

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.hall_sensor_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self._rpm_counter = 0

        def cb(channel):
            self._rpm_counter = self._rpm_counter + 1

        GPIO.add_event_detect(self.hall_sensor_pin, GPIO.RISING, callback=cb)
        time.sleep(seconds)
        GPIO.remove_event_detect(self.hall_sensor_pin)
        GPIO.cleanup(self.hall_sensor_pin)

        return self._rpm_counter

    def stop_stirring(self):
        # if the user unpauses, we want to go back to their previous value, and not the default.
        self.set_duty_cycle(0)

    def on_ready_to_sleeping(self):
        self._previous_duty_cycle = self.duty_cycle
        self.stop_stirring()

    def on_sleeping_to_ready(self):
        self.duty_cycle = self._previous_duty_cycle
        self.start_stirring()

    def set_duty_cycle(self, value):
        self.duty_cycle = clamp(0, round(float(value), 5), 100)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def set_target_rpm(self, value):
        self.rpm_check_thread.pause()

        self.target_rpm = float(value)
        self.pid.set_setpoint(self.target_rpm)

        # we need to start the feedback loop here to orient close to our desired value
        # TODO: we should move this outside of this MQTT callback...
        while True:
            error = self.poll_and_update_dc(4)
            if (
                abs(error) < 0.15
            ):  # TODO: I don't like this check, it will tend to overshoot.
                break
            time.sleep(0.1)  # sleep for a moment to "apply" the new DC.

        self.rpm_check_thread.unpause()


def start_stirring(target_rpm=0, unit=None, experiment=None) -> Stirrer:
    unit = unit or get_unit_name()
    experiment = experiment or get_latest_experiment_name()

    stirrer = Stirrer(
        target_rpm=target_rpm,
        unit=unit,
        experiment=experiment,
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
def click_stirring(target_rpm):
    """
    Start the stirring of the Pioreactor.
    """
    start_stirring(
        target_rpm=target_rpm,
    )
    signal.pause()
