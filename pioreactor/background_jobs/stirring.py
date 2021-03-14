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


GPIO.setmode(GPIO.BCM)
JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]
logger = logging.getLogger(JOB_NAME)

unit = get_unit_name()


class Stirrer(BackgroundJob):
    """
    Send message to "pioreactor/{unit}/{experiment}/stirring/duty_cycle/set" to change the stirring speed.
    """

    editable_settings = ["duty_cycle"]

    def __init__(self, duty_cycle, unit, experiment, hertz=50):
        super(Stirrer, self).__init__(job_name=JOB_NAME, unit=unit, experiment=experiment)

        self.hertz = hertz
        self.pin = PWM_TO_PIN[config.getint("PWM", "stirring")]

        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, 0)
        self.pwm = GPIO.PWM(self.pin, self.hertz)
        self.set_duty_cycle(duty_cycle)
        self.start_stirring()

    def on_disconnect(self):
        # not necessary, but will update the UI to show that the speed is 0 (off)
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

    def __setattr__(self, name, value):
        if name == "state":
            if value != self.READY:
                try:
                    self.stop_stirring()
                except AttributeError:
                    pass
            elif (value == self.READY) and (self.state == self.SLEEPING):
                self.duty_cycle = self._previous_duty_cycle
                self.start_stirring()
        super(Stirrer, self).__setattr__(name, value)

    def set_duty_cycle(self, value):
        self.duty_cycle = int(value)
        self.pwm.ChangeDutyCycle(self.duty_cycle)


def stirring(duty_cycle=0, duration=None):
    experiment = get_latest_experiment_name()

    try:
        stirrer = Stirrer(duty_cycle, unit=unit, experiment=experiment)
        stirrer.start_stirring()

        if duration is None:
            signal.pause()
        else:
            time.sleep(duration)

    except Exception as e:
        GPIO.cleanup()
        logger.error(f"failed with {str(e)}")
        raise e

    return


@click.command(name="stirring")
@click.option(
    "--duty-cycle",
    default=config.getint("stirring", f"duty_cycle_{unit}", fallback=0),
    help="set the duty cycle",
    show_default=True,
    type=click.IntRange(0, 100, clamp=True),
)
def click_stirring(duty_cycle):
    """
    Start the stirring of the Pioreactor.
    """
    stirring(duty_cycle=duty_cycle)
