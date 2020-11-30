# -*- coding: utf-8 -*-
import time, os, traceback, signal, sys

import click
import RPi.GPIO as GPIO


from pioreactor.whoami import unit, experiment
from pioreactor.config import config
from pioreactor.pubsub import publish
from pioreactor.utils.timing import every
from pioreactor.background_jobs import BackgroundJob

GPIO.setmode(GPIO.BCM)
JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class Stirrer(BackgroundJob):
    """
    Send message to "pioreactor/{unit}/{experiment}/stirring/duty_cycle/set" to change the stirring speed.
    """

    editable_settings = ["duty_cycle"]

    def __init__(self, duty_cycle, unit, experiment, verbose=0, hertz=50, pin=int(config["rpi_pins"]["fan"])):
        super(Stirrer, self).__init__(job_name=JOB_NAME, verbose=verbose, unit=unit, experiment=experiment)

        self.hertz = hertz
        self.pin = pin

        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, 0)
        self.pwm = GPIO.PWM(self.pin, self.hertz)
        self.set_duty_cycle(duty_cycle)
        self.start_stirring()

    def on_disconnect(self):
        # not necessary, but will update the UI to show that the speed is 0 (off)
        self.set_duty_cycle(0)
        GPIO.cleanup()

    def start_stirring(self):
        self.pwm.start(90)  # get momentum to start
        time.sleep(0.25)
        self.pwm.ChangeDutyCycle(self.duty_cycle)

    def stop_stirring(self):
        self.pwm.stop()

    def __setattr__(self, name, value):
        if name == "state":
            if value != self.READY:
                try:
                    self.stop_stirring()
                except:
                    pass
        super(Stirrer, self).__setattr__(name, value)

    def set_duty_cycle(self, value):
        self.duty_cycle = value
        self.pwm.ChangeDutyCycle(self.duty_cycle)


def stirring(duty_cycle=int(config["stirring"][f"duty_cycle{unit}"]), duration=None, verbose=0):
    try:
        print("here1")
        stirrer = Stirrer(duty_cycle, unit, experiment)
        print("here2")

        stirrer.start_stirring()
        print("here3")

        if duration is None:

            signal.pause()
        else:
            time.sleep(duration)

    except Exception as e:
        GPIO.cleanup()
        publish(f"pioreactor/{unit}/{experiment}/error_log", f"[stirring] failed with {str(e)}", verbose=verbose)
        raise e
    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--duty-cycle", default=int(config["stirring"][f"duty_cycle{unit}"]), help="set the duty cycle")
@click.option(
    "--verbose", "-v", count=True, help="print to std. out (may be redirected to pioreactor.log). Increasing values log more."
)
def click_stirring(duty_cycle, verbose):
    print("here0")

    stirring(duty_cycle=duty_cycle, verbose=verbose)


if __name__ == "__main__":
    click_stirring()
