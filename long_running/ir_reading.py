from statistics import stdev, mean
import configparser
import time

from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
from  paho.mqtt import publish
import board
import busio

config = configparser.ConfigParser()
config.read('config.ini')


class MovingStats():
    def __init__(self, lookback=5):
        self.values = [None] * lookback
        self._lookback = lookback

    def update(self, new_value):
        self.values.pop(0)
        self.values.append(new_value)
        assert len(self.values) == self._lookback

    def mean(self):
        try:
            return mean(self.values)
        except:
            pass

    def std(self):
        try:
            return stdev(self.values)
        except:
            pass



GAIN = int(config['ir_reading']['gain'])
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, gain=GAIN)
chan = AnalogIn(ads, ADS.P0)

sm = MovingStats(lookback=int(config['ir_reading']['lookback']))

while True:
    time.sleep(1.0)
    try:
        raw_signal = chan.value
        sm.update(raw_signal)
        if sm.mean() is not None:
            publish.single("morbidostat/IR1_moving_average", sm.mean())
            publish.single("morbidostat/IR1_moving_std", sm.std())
            publish.single("morbidostat/IR1_raw", v)

    except Exception:
        publish.single("morbidostat/log", "ir_reading.py failed")
        break

