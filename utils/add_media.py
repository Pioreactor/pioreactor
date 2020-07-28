# add media
import click
import RPi.GPIO as GPIO
import time
config = configparser.ConfigParser()
config.read('config.ini')


@click.command()
@click.argument('mL')
def add_media(mL):
    GPIO.setmode(GPIO.BCM)

    MEDIA_PIN = config['rpi_pins']['media']
    GPIO.setup(MEDIA_PIN, GPIO.OUT)
    GPIO.output(MEDIA_PIN, 1)

    GPIO.output(MEDIA_PIN, 0)
    time.sleep(ml / config['pump_calibration']['media_ml_per_second'])
    GPIO.output(MEDIA_PIN, 1)

    return

if __name__ == '__main__':
    add_media()