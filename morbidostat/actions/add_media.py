# -*- coding: utf-8 -*-
# add media
import time
from json import loads
import click
import RPi.GPIO as GPIO
from morbidostat.utils import pump_ml_to_duration
from morbidostat.utils import config, get_unit_from_hostname
from morbidostat.utils.pubsub import publish


def add_media(ml=None, duration=None, duty_cycle=None, verbose=False):
    unit = get_unit_from_hostname()
    hz = 100

    try:
        GPIO.setmode(GPIO.BCM)

        MEDIA_PIN = int(config["rpi_pins"]["media"])
        GPIO.setup(MEDIA_PIN, GPIO.OUT)
        GPIO.output(MEDIA_PIN, 0)
        pwm = GPIO.PWM(MEDIA_PIN, hz)

        pwm.start(duty_cycle)

        if ml is not None:
            time.sleep(pump_ml_to_duration(ml, *loads(config["pump_calibration"][f"media{unit}_ml_calibration"])))
        else:
            time.sleep(duration)

        pwm.stop()
        GPIO.output(MEDIA_PIN, 0)

        publish(f"morbidostat/{unit}/io_events", '{"volume_change": "%s", "event": "add_media"}' % ml, verbose=verbose)
        publish(f"morbidostat/{unit}/log", "add media: %smL" % ml, verbose=verbose)
    except Exception as e:
        publish(f"morbidostat/{unit}/error_log", f"[add_media]: failed with {str(e)}", verbose=verbose)
        raise e
    finally:
        GPIO.cleanup()
    return


@click.command()
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--duty_cycle", type=int)
@click.option("--verbose", is_flag=True, help="print to std out")
def click_add_media(ml, duration, duty_cycle, verbose):
    assert (ml is not None) or (duration is not None)
    assert not ((ml is not None) and (duration is not None)), "Only select ml or duration"
    return add_media(ml, duration, duty_cycle, verbose)


if __name__ == "__main__":
    click_add_media()
