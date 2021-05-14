# -*- coding: utf-8 -*-

import time, signal, sys

import click

from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.hardware_mappings import PWM_TO_PIN, HALL_SENSOR_PIN
from pioreactor.pubsub import subscribe
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.pwm import PWM
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage, PID

if is_testing_env():
    import fake_rpi

    sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
    sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO

import RPi.GPIO as GPIO


GPIO.setmode(GPIO.BCM)
JOB_NAME = "stirring"


def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))


class Stirrer(BackgroundJob):
    """
    Parameters
    ------------
    TODO

    """

    editable_settings = ["rpm", "rpm_increase_between_adc_readings"]
    delta_between_updates = 16
    _time_of_last_detected = None

    def __init__(
        self, rpm, unit, experiment, hertz=50, rpm_increase_between_adc_readings=False
    ):
        super(Stirrer, self).__init__(job_name=JOB_NAME, unit=unit, experiment=experiment)

        self.logger.debug(f"Starting stirring with initial RPM {rpm}.")
        self.set_rpm(rpm)
        self.set_rpm_increase_between_adc_readings(rpm_increase_between_adc_readings)

        self.pwm = PWM(PWM_TO_PIN[config.getint("PWM", "stirring")], hertz)
        self.rpm_ema = ExponentialMovingAverage(0.50)

        Kp = config.getfloat("stirring.PID", "Kp")
        Ki = config.getfloat("stirring.PID", "Ki")
        Kd = config.getfloat("stirring.PID", "Kd")

        self.pid = PID(
            Kp,
            Ki,
            Kd,
            setpoint=self.rpm,
            sample_time=None,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="rpm",
        )

        self.set_duty_cycle(50)
        self.start_stirring()
        self.setup_GPIO_for_hall_sensor()

        self.pid_rpm_thread = RepeatedTimer(
            self.delta_between_updates, self.update_duty_cycle_to_match_desired_rpm
        )
        self.pid_rpm_thread.start()

    def update_duty_cycle_to_match_desired_rpm(self):
        try:
            if self.rpm_ema.value is None:
                return
            new_dc_delta = self.pid.update(
                self.rpm_ema.value, dt=self.delta_between_updates
            )
            print(self.rpm_ema.value, new_dc_delta)
            self.set_duty_cycle(self.duty_cycle + new_dc_delta)
        except Exception:
            import traceback

            traceback.print_exc()

    def _magnet_detected_callback(self, *args):
        try:
            if self._time_of_last_detected is None:
                self._time_of_last_detected = time.time()
            else:
                current_time = time.time()
                delta = current_time - self._time_of_last_detected
                self.rpm_ema.update(60 / delta)  # convert from seconds to RPM
                print(self.rpm_ema.value)
                self._time_of_last_detected = current_time
        except Exception:
            import traceback

            traceback.print_exc()

    def on_disconnect(self):
        if hasattr(self, "sneak_in_timer"):
            self.sneak_in_timer.cancel()

        # not necessary, but will update the UI to show that the speed is 0 (off)
        self.stop_stirring()
        self.pwm.stop()
        self.pwm.cleanup()
        GPIO.cleanup(HALL_SENSOR_PIN)

    def setup_GPIO_for_hall_sensor(self):
        GPIO.setup(HALL_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(
            HALL_SENSOR_PIN, GPIO.FALLING, callback=self._magnet_detected_callback
        )

    def start_stirring(self):
        self.pwm.start(100)  # get momentum to start
        time.sleep(0.5)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def stop_stirring(self):
        # if the user unpauses, we want to go back to their previous value, and not the default.
        self._previous_rpm = self.rpm
        self._previous_duty_cycle = self.duty_cycle
        self.set_duty_cycle(0)
        self.set_rpm(0)

    def set_rpm(self, value):
        self.rpm = int(value)
        try:
            self.pid.set_setpoint(self.rpm)
        except AttributeError:
            pass

    def set_state(self, new_state):
        if new_state != self.READY:
            try:
                self.stop_stirring()
            except AttributeError:
                pass
        elif (new_state == self.READY) and (self.state == self.SLEEPING):
            self.rpm = self._previous_rpm
            self.duty_cycle = self._previous_duty_cycle
            self.start_stirring()
        super(Stirrer, self).set_state(new_state)

    def set_duty_cycle(self, value):
        self.duty_cycle = clamp(0, round(float(value)), 100)
        print(self.duty_cycle)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def set_rpm_increase_between_adc_readings(self, rpm_increase_between_adc_readings):
        self.rpm_increase_between_adc_readings = int(rpm_increase_between_adc_readings)
        if not self.rpm_increase_between_adc_readings:
            self.sub_client.message_callback_remove(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time"
            )
            try:
                self.sneak_in_timer.cancel()
            except AttributeError:
                pass

        else:
            self.subscribe_and_callback(
                self.start_or_stop_sneaking,
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time",
            )

    def start_or_stop_sneaking(self, msg):
        if msg.payload:
            self.sneak_action_between_readings(0.6, 2.5)
        else:
            try:
                self.sneak_in_timer.cancel()
            except AttributeError:
                pass

    def sneak_action_between_readings(self, post_duration, pre_duration):
        """
        post_duration: how long to wait (seconds) after the ADS reading before running sneak_in
        pre_duration: duration between stopping the action and the next ADS reading
        """

        try:
            self.sneak_in_timer.cancel()
        except AttributeError:
            pass

        def sneak_in():
            if self.state != self.READY:
                return

            factor = (
                1.4
            )  # this could be a config param? Once RPM is established, maybe a max is needed.
            original_dc = self.duty_cycle
            self.set_duty_cycle(factor * self.duty_cycle)
            time.sleep(ads_interval - (post_duration + pre_duration))
            self.set_duty_cycle(original_dc)

        # this could fail in the following way:
        # in the same experiment, the od_reading fails so that the ADC attributes are never
        # cleared. Later, this job starts, and it will pick up the _old_ ADC attributes.
        ads_start_time = float(
            subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time"
            ).payload
        )

        ads_interval = float(
            subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval"
            ).payload
        )

        # get interval, and confirm that the requirements are possible: post_duration + pre_duration <= ADS interval
        if ads_interval <= (post_duration + pre_duration):
            raise ValueError(
                "Your samples_per_second is too high to add in dynamic stirring."
            )

        self.sneak_in_timer = RepeatedTimer(ads_interval, sneak_in, run_immediately=False)

        time_to_next_ads_reading = ads_interval - (
            (time.time() - ads_start_time) % ads_interval
        )

        time.sleep(time_to_next_ads_reading + post_duration)
        self.sneak_in_timer.start()


def stirring(rpm=0, rpm_increase_between_adc_readings=False, duration=None):
    experiment = get_latest_experiment_name()

    stirrer = Stirrer(
        rpm,
        rpm_increase_between_adc_readings=rpm_increase_between_adc_readings,
        unit=get_unit_name(),
        experiment=experiment,
    )
    stirrer.start_stirring()

    if duration is None:
        signal.pause()
    else:
        time.sleep(duration)


@click.command(name="stirring")
@click.option(
    "--rpm",
    default=config.getint("stirring", "rpm", fallback=0),
    help="set the duty cycle",
    show_default=True,
    type=click.IntRange(0, 1000, clamp=True),
)
@click.option("--rpm-increase-between-adc-readings", is_flag=True)
def click_stirring(rpm, rpm_increase_between_adc_readings):
    """
    Start the stirring of the Pioreactor.
    """
    stirring(rpm=rpm, rpm_increase_between_adc_readings=rpm_increase_between_adc_readings)
