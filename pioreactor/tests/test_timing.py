# -*- coding: utf-8 -*-
# test_timing.py
from __future__ import annotations

import time

import pytest

from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime
from pioreactor.utils.timing import to_iso_format


def test_inverse_relationship():

    dt = current_utc_datetime()
    assert dt == to_datetime(to_iso_format(dt))


def test_repeated_timer_will_not_execute_if_killed_during_run_immediately_paused():
    class Counter:

        counter = 0

        def __init__(self):

            self.thread = RepeatedTimer(5, self.run, run_immediately=True, run_after=60).start()

        def run(self):
            self.counter += 1

    c = Counter()
    c.thread.join()

    assert c.counter == 0


def test_repeated_timer_has_low_variance():
    import time
    import numpy as np

    interval = 0.01
    data = []

    def run():
        data.append(time.perf_counter())

    t = RepeatedTimer(interval, run).start()
    time.sleep(5)
    t.cancel()

    delta = np.diff(np.array(data))
    mean = np.mean(delta)
    std = np.std(delta)

    assert (mean - interval) < 1e-3
    assert std < 0.005

    # try a new interval, show it has similar std.
    interval = 4 * interval
    data2 = []

    def run2():
        data2.append(time.perf_counter())

    t = RepeatedTimer(interval, run2).start()
    time.sleep(4 * 5)  # scale to collect similar amounts of data points
    t.cancel()

    delta = np.diff(np.array(data2))
    mean = np.mean(delta)
    std = np.std(delta)

    assert (mean - interval) < 1e-3
    assert std < 0.005


def test_repeated_timer_has_low_variance_even_for_noisy_process():
    import time
    import numpy as np

    interval = 0.2
    data = []

    def run():
        data.append(time.perf_counter())
        time.sleep(0.05 * np.random.random())

    t = RepeatedTimer(interval, run).start()
    time.sleep(5)
    t.cancel()

    delta = np.diff(np.array(data))
    mean = np.mean(delta)
    std = np.std(delta)

    assert (mean - interval) < 1e-3
    assert std < 0.005


def test_repeated_timer_run_immediately_works_as_intended():
    class Counter:

        counter = 0

        def __init__(self, run_immediately):

            self.thread = RepeatedTimer(
                5,
                self.run,
                run_immediately=run_immediately,
            ).start()

        def run(self):
            self.counter += 1

    c = Counter(run_immediately=True)
    time.sleep(6)
    c.thread.join()
    assert c.counter == 2

    c = Counter(run_immediately=False)
    time.sleep(6)
    c.thread.join()
    assert c.counter == 1


def test_repeated_timer_run_after_works_as_intended():
    class Counter:

        counter = 0

        def __init__(self, run_after):

            self.thread = RepeatedTimer(
                5, self.run, run_immediately=True, run_after=run_after
            ).start()

        def run(self):
            self.counter += 1

    c = Counter(run_after=0)
    time.sleep(3)
    c.thread.join()
    assert c.counter == 1

    c = Counter(run_after=5)
    time.sleep(3)
    c.thread.join()
    assert c.counter == 0


def test_repeated_timer_pause_works_as_intended():
    class Counter:

        counter = 0

        def __init__(self):

            self.thread = RepeatedTimer(
                3,
                self.run,
                run_immediately=True,
            ).start()

        def run(self):
            self.counter += 1

    c = Counter()
    time.sleep(4)
    assert c.counter == 2

    c.thread.pause()
    time.sleep(5)
    assert c.counter == 2
    c.thread.unpause()

    time.sleep(5)
    assert c.counter > 2
