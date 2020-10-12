# -*- coding: utf-8 -*-
"""
Continuously take an optical density reading (more accurately: a backscatter reading, which is a proxy for OD).
This script is designed to run in a background process and push data to MQTT.

>>> nohup python3 -m morbidostat.background_jobs.od_reading &
"""
import time, os, traceback, signal, sys

import click
import RPi.GPIO as GPIO

from morbidostat.utils import config, get_latest_experiment_name, unit
from morbidostat.utils.pubsub import publish, subscribe_and_callback
from morbidostat.utils.timing import every

GPIO.setmode(GPIO.BCM)


class Stirrer:
    def __init__(self, duty_cycle, unit, experiment, verbose=0, hertz=50, pin=int(config["rpi_pins"]["fan"])):
        assert 0 <= duty_cycle <= 100
        self.unit = unit
        self.verbose = verbose
        self.experiment = experiment

        self.hertz = hertz
        self.pin = pin
        self.duty_cycle = duty_cycle

        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, 0)

        self.pwm = GPIO.PWM(self.pin, self.hertz)
        self.start_passive_listener_on_duty_cycle()

    def change_duty_cycle(self, new_duty_cycle):
        assert 0 <= new_duty_cycle <= 100
        old_duty_cycle = self.duty_cycle
        self.duty_cycle = new_duty_cycle
        self.pwm.ChangeDutyCycle(self.duty_cycle)
        publish(
            f"morbidostat/{self.unit}/{self.experiment}/log",
            f"[stirring]: changed duty cycle from {old_duty_cycle} to {self.duty_cycle}",
            verbose=self.verbose,
        )

    def start_stirring(self):
        self.pwm.start(95)  # get momentum to start
        time.sleep(0.25)
        self.pwm.ChangeDutyCycle(self.duty_cycle)

    def stop_stirring(self):
        self.pwm.stop()
        GPIO.cleanup()

    def start_passive_listener_on_duty_cycle(self):
        job_name = os.path.splitext(os.path.basename((__file__)))[0]
        topic = f"morbidostat/{self.unit}/{self.experiment}/{job_name}/duty_cycle"

        def callback(msg):
            self.change_duty_cycle(int(msg.payload))

        subscribe_and_callback(callback, topic)


def stirring(duty_cycle, verbose=0, duration=None):
    # duration is for testing

    def terminate(*args):
        GPIO.cleanup()
        sys.exit()

    signal.signal(signal.SIGTERM, terminate)

    experiment = get_latest_experiment_name()

    publish(f"morbidostat/{unit}/{experiment}/log", f"[stirring]: start stirring with duty cycle={duty_cycle}", verbose=verbose)

    try:
        stirrer = Stirrer(duty_cycle, unit, experiment)
        stirrer.start_stirring()

        if duration is None:
            signal.pause()
        else:
            time.sleep(duration)

    except Exception as e:
        publish(f"morbidostat/{unit}/{experiment}/error_log", f"[stirring] failed with {str(e)}", verbose=verbose)
        raise e
    finally:
        stirrer.stop_stirring()
        GPIO.cleanup()
    return


@click.command()
@click.option("--duty_cycle", default=int(config["stirring"][f"duty_cycle{unit}"]), help="set the duty cycle")
@click.option(
    "--verbose", default=0, help="print to std. out (may be redirected to morbidostat.log). Increasing values log more."
)
def click_stirring(duty_cycle, verbose):
    stirring(duty_cycle, verbose=verbose)


if __name__ == "__main__":
    click_stirring()
