# remove waste
import time
import configparser
import click
import RPi.GPIO as GPIO

config = configparser.ConfigParser()
config.read('config.ini')


@click.command()
@click.argument('ml', type=int)
def remove_waste(ml):
    GPIO.setmode(GPIO.BCM)

    WASTE_PIN = int(config['rpi_pins']['waste'])
    GPIO.setup(WASTE_PIN, GPIO.OUT)
    GPIO.output(WASTE_PIN, 1)

    GPIO.output(WASTE_PIN, 0)
    time.sleep(ml / float(config['pump_calibration']['waste_ml_per_second']))
    GPIO.output(WASTE_PIN, 1)

    return

if __name__ == '__main__':
    try:
        remove_waste()
    except:
        GPIO.cleanup()