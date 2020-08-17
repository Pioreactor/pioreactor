# add media
import time
import configparser
import click
from  paho.mqtt import publish
import RPi.GPIO as GPIO

config = configparser.ConfigParser()
config.read('config.ini')


@click.command()
@click.argument('ml', type=float)
def add_media(ml):

    morbidostat = "morbidostat1"

    GPIO.setmode(GPIO.BCM)

    MEDIA_PIN = int(config['rpi_pins']['media1'])
    GPIO.setup(MEDIA_PIN, GPIO.OUT)
    GPIO.output(MEDIA_PIN, 1)

    click.echo(click.style("starting add_media: %smL" % ml, fg='green'))

    GPIO.output(MEDIA_PIN, 0)
    time.sleep(ml / float(config['pump_calibration']['media_ml_per_second']))
    GPIO.output(MEDIA_PIN, 1)

    publish.single(f"{morbidostat}/log", "add_media: %smL" % ml)
    publish.single(f"{morbidostat}/io_events", '{"volume_change": "%s", "event": "add_media"}' % ml)
    click.echo(click.style("finished add_media: %smL" % ml, fg='green'))

    GPIO.cleanup()
    return

if __name__ == '__main__':
    try:
        add_media()
    except Exception as e:
        print(e)
    GPIO.cleanup()