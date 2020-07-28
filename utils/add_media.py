# add media
import time
import configparser
import click
import RPi.GPIO as GPIO

config = configparser.ConfigParser()
config.read('config.ini')


@click.command()
@click.argument('ml', type=int)
def add_media(ml):
    GPIO.setmode(GPIO.BCM)

    MEDIA_PIN = int(config['rpi_pins']['media'])
    GPIO.setup(MEDIA_PIN, GPIO.OUT)
    GPIO.output(MEDIA_PIN, 1)

    GPIO.output(MEDIA_PIN, 0)
    time.sleep(ml / float(config['pump_calibration']['media_ml_per_second']))
    GPIO.output(MEDIA_PIN, 1)

    return

if __name__ == '__main__':
    try:
        add_media()
    except:
        GPIO.cleanup()