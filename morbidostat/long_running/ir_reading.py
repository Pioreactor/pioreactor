from morbidostat.utils.streaming import LowPassFilter
from statistics import stdev, mean
import configparser
import time
import click
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
from  paho.mqtt import publish
import board
import busio



config = configparser.ConfigParser()
config.read('config.ini')


i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
chan = AnalogIn(ads, ADS.P0)

sm = LowPassFilter(60, 0.0001, 1)

while True:
    time.sleep(1.0)
    try:
        raw_signal = chan.voltage
        sm.update(raw_signal)
        if sm.latest_reading is not None:
            publish.single("morbidostat/IR1_low_ass", sm.latest_reading)
            publish.single("morbidostat/IR1_raw", raw_signal)

    except Exception as e:
        publish.single("morbidostat/log", "ir_reading.py failed")
        raise e
        break

