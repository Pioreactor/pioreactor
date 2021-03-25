# -*- coding: utf-8 -*-

import time, os, sys, signal
import logging

import click

if "pytest" in sys.modules or os.environ.get("TESTING"):
    import fake_rpi

    sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
    sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO

import RPi.GPIO as GPIO
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.pubsub import subscribe
from pioreactor.utils.timing import RepeatedTimer


GPIO.setmode(GPIO.BCM)
JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))


class Stirrer(BackgroundJob):
    """
    Parameters
    ------------


    duty_cycle: int
        Send message to "pioreactor/{unit}/{experiment}/stirring/duty_cycle/set" to change the stirring speed.

    dc_increase_between_adc_readings: bool
         listen for ADC reading events, and increasing stirring when not reading.

    """

    editable_settings = ["duty_cycle", "dc_increase_between_adc_readings"]

    def __init__(
        self,
        duty_cycle,
        unit,
        experiment,
        hertz=50,
        dc_increase_between_adc_readings=False,
    ):
        super(Stirrer, self).__init__(job_name=JOB_NAME, unit=unit, experiment=experiment)

        self.hertz = hertz
        self.pin = PWM_TO_PIN[config.getint("PWM", "stirring")]
        self.set_dc_increase_between_adc_readings(dc_increase_between_adc_readings)

        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, 0)
        self.pwm = GPIO.PWM(self.pin, self.hertz)
        self.set_duty_cycle(duty_cycle)
        self.start_stirring()

    def on_disconnect(self):
        # not necessary, but will update the UI to show that the speed is 0 (off)
        if hasattr(self, "sneak_in_timer"):
            self.sneak_in_timer.cancel()

        self.stop_stirring()
        GPIO.cleanup()

    def start_stirring(self):
        self.pwm.start(100)  # get momentum to start
        time.sleep(0.5)
        self.pwm.ChangeDutyCycle(self.duty_cycle)

    def stop_stirring(self):
        # if the user unpauses, we want to go back to their previous value, and not the default.
        self._previous_duty_cycle = self.duty_cycle
        self.set_duty_cycle(0)

    def set_state(self, new_state):
        if new_state != self.READY:
            try:
                self.stop_stirring()
            except AttributeError:
                pass
        elif (new_state == self.READY) and (self.state == self.SLEEPING):
            self.duty_cycle = self._previous_duty_cycle
            self.start_stirring()
        super(Stirrer, self).set_state(new_state)

    def set_duty_cycle(self, value):
        self.duty_cycle = clamp(0, round(value), 100)
        self.pwm.ChangeDutyCycle(self.duty_cycle)

    def set_dc_increase_between_adc_readings(self, dc_increase_between_adc_readings):

        self.dc_increase_between_adc_readings = int(dc_increase_between_adc_readings)
        if not self.dc_increase_between_adc_readings:
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
            self.sneak_in_timer.cancel()

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
            factor = (
                1.4
            )  # this could be a config param? Once RPM is established, maybe a max is needed.
            self.set_duty_cycle(factor * self.duty_cycle)
            time.sleep(ads_interval - (post_duration + pre_duration))
            self.set_duty_cycle(self.duty_cycle / factor)

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


def stirring(duty_cycle=0, dc_increase_between_adc_readings=False, duration=None):
    experiment = get_latest_experiment_name()

    try:
        stirrer = Stirrer(
            duty_cycle,
            dc_increase_between_adc_readings=dc_increase_between_adc_readings,
            unit=get_unit_name(),
            experiment=experiment,
        )
        stirrer.start_stirring()

        if duration is None:
            signal.pause()
        else:
            time.sleep(duration)

    except Exception as e:
        GPIO.cleanup()
        logger = logging.getLogger(JOB_NAME)
        logger.error(f"failed with {str(e)}")
        raise e

    return


@click.command(name="stirring")
@click.option(
    "--duty-cycle",
    default=config.getint("stirring", "duty_cycle", fallback=0),
    help="set the duty cycle",
    show_default=True,
    type=click.IntRange(0, 100, clamp=True),
)
@click.option("--dc-increase-between-adc-readings", is_flag=True)
def click_stirring(duty_cycle, dc_increase_between_adc_readings):
    """
    Start the stirring of the Pioreactor.
    """
    stirring(
        duty_cycle=duty_cycle,
        dc_increase_between_adc_readings=dc_increase_between_adc_readings,
    )
