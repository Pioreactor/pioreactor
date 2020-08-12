from statistics import stdev, mean
import configparser
import time

import click
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
from  paho.mqtt import publish
import board
import busio

from morbidostat.utils.streaming import LowPassFilter



config = configparser.ConfigParser()
config.read('config.ini')


i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, data_rate=8, gain=8)
chan = AnalogIn(ads, ADS.P0, ADS.P1)
sampling_rate = 1/float(config['ir_sampling']['samples_per_second'])

sm = LowPassFilter(200, 0.0001, sampling_rate)

i = 0
while True:
    time.sleep(sampling_rate)
    try:
        raw_signal = chan.voltage
        sm.update(raw_signal)
        if sm.latest_reading is not None and i % 100 == 0:
            publish.single("morbidostat/IR1_low_pass", sm.latest_reading)
            publish.single("morbidostat/IR1_raw", raw_signal)
        print(raw_signal, sm.latest_reading)
        i+=1

    except OSError as e:
        # just pause, not sure why this happens when add_media o remove_waste are called.
        time.sleep(5.0)
    except Exception as e:
        publish.single("morbidostat/log", "ir_reading.py failed")
        raise e
        break

