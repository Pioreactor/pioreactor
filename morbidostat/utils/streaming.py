from scipy import signal
from statistics import *


class MovingStats:
    def __init__(self, lookback=5):
        self.values = [None] * lookback
        self._lookback = lookback

    def update(self, new_value):
        self.values.pop(0)
        self.values.append(new_value)
        assert len(self.values) == self._lookback

    @property
    def mean(self):
        try:
            return mean(self.values)
        except:
            pass

    @property
    def std(self):
        try:
            return stdev(self.values)
        except:
            pass


class LowPassFilter:
    def __init__(self, length_of_filter, low_pass_corner_frequ, time_between_reading):

        self._latest_reading = None
        self.filtwindow = signal.firwin(length_of_filter, low_pass_corner_frequ, fs=1 / time_between_reading)
        self.window = signal.lfilter_zi(self.filtwindow, 1)

    def update(self, value):
        self._latest_reading, self.window = signal.lfilter(self.filtwindow, 1, [value], zi=self.window)

    @property
    def latest_reading(self):
        return self._latest_reading[0]
