# remove waste
import time
import configparser
import click
import RPi.GPIO as GPIO
from  paho.mqtt import publish

config = configparser.ConfigParser()
config.read('config.ini')


def remove_waste(ml, unit):

    try:
        GPIO.setmode(GPIO.BCM)

        WASTE_PIN = int(config['rpi_pins'][f'waste{unit}'])
        GPIO.setup(WASTE_PIN, GPIO.OUT)
        GPIO.output(WASTE_PIN, 1)

        # this should be a decorator at some point
        click.echo(click.style("starting remove_waste: %smL" % ml, fg='green'))

        GPIO.output(WASTE_PIN, 0)
        time.sleep(ml / float(config['pump_calibration']['waste_ml_per_second']))
        GPIO.output(WASTE_PIN, 1)

        publish.single(f"morbidostat/{unit}/log", "remove_waste: %smL" % ml)
        publish.single(f"morbidostat/{unit}/io_events", '{"volume_change": "-%s", "event": "remove_waste"}' % ml)
        click.echo(click.style("finished remove_waste: %smL" % ml, fg='green'))
    except Exception as e:
        publish.single(f"morbidostat/{unit}/error_log", f"{unit} remove_waste.py failed with {str(e)}")
    finally:
        GPIO.cleanup()
    return

@click.command()
@click.option('--unit', default="1", help='The morbidostat unit')
@click.argument('ml', type=float)
def click_remove_waste(ml, unit):
    return remove_waste(ml, unit)

if __name__ == '__main__':
    click_remove_waste()
