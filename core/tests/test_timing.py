# -*- coding: utf-8 -*-
# test_timing.py
from __future__ import annotations

import datetime
import time
from threading import Event

import pytest
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.timing import to_datetime
from pioreactor.utils.timing import to_iso_format


def test_inverse_relationship() -> None:
    dt = current_utc_datetime()
    assert dt == to_datetime(to_iso_format(dt))


def test_to_datetime() -> None:
    assert to_datetime("2010-01-01T00:00:00Z") == datetime.datetime(
        2010, 1, 1, 0, 0, tzinfo=datetime.timezone.utc
    )
    assert to_datetime("2010-01-01T00:00:00.000Z") == datetime.datetime(
        2010, 1, 1, 0, 0, tzinfo=datetime.timezone.utc
    )


def test_repeated_timer_will_not_execute_if_killed_during_run_immediately_paused() -> None:
    class Counter:
        counter = 0

        def __init__(self) -> None:
            self.thread = RepeatedTimer(5, self.run, run_immediately=True, run_after=60).start()

        def run(self) -> None:
            self.counter += 1

    c = Counter()
    c.thread.join()

    assert c.counter == 0


@pytest.mark.slow
def test_repeated_timer_has_low_variance() -> None:
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


def test_repeated_timer_has_low_variance_even_for_noisy_process() -> None:
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


@pytest.mark.slow
def test_repeated_timer_run_immediately_works_as_intended() -> None:
    class Counter:
        counter = 0

        def __init__(self, run_immediately) -> None:
            self.thread = RepeatedTimer(
                5,
                self.run,
                run_immediately=run_immediately,
            ).start()

        def run(self) -> None:
            self.counter += 1

    c = Counter(run_immediately=True)
    time.sleep(6)
    c.thread.join()
    assert c.counter == 2

    c = Counter(run_immediately=False)
    time.sleep(6)
    c.thread.join()
    assert c.counter == 1


def test_repeated_timer_run_after_works_as_intended() -> None:
    class Counter:
        counter = 0

        def __init__(self, run_after) -> None:
            self.thread = RepeatedTimer(5, self.run, run_immediately=True, run_after=run_after).start()

        def run(self) -> None:
            self.counter += 1

    c = Counter(run_after=0)
    time.sleep(3)
    c.thread.join()
    assert c.counter == 1

    c = Counter(run_after=5)
    time.sleep(3)
    c.thread.join()
    assert c.counter == 0


@pytest.mark.slow
def test_repeated_timer_pause_works_as_intended() -> None:
    class Counter:
        counter = 0

        def __init__(self) -> None:
            self.thread = RepeatedTimer(
                3,
                self.run,
                run_immediately=True,
            ).start()

        def run(self) -> None:
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


def test_repeated_timer_run_immediately() -> None:
    event = Event()

    def sample_function():
        event.set()

    rt = RepeatedTimer(2, sample_function, run_immediately=True)
    rt.start()
    assert event.wait(1)
    rt.cancel()


def test_repeated_timer_pause_unpause() -> None:
    counter = [0]

    def sample_function():
        counter[0] += 1

    rt = RepeatedTimer(0.5, sample_function)
    rt.start()
    time.sleep(1)
    rt.pause()
    current_count = counter[0]
    time.sleep(1)
    assert counter[0] == current_count
    rt.unpause()
    time.sleep(1)
    assert counter[0] > current_count
    rt.cancel()


def test_repeated_timer_args_kwargs() -> None:
    event = Event()

    def sample_function(arg1, kwarg1=None):
        assert arg1 == "test_arg"
        assert kwarg1 == "test_kwarg"
        event.set()

    rt = RepeatedTimer(1, sample_function, args=("test_arg",), kwargs={"kwarg1": "test_kwarg"})
    rt.start()
    assert event.wait(2)
    rt.cancel()


def test_repeated_timer_cancel() -> None:
    counter = [0]

    def sample_function():
        counter[0] += 1

    rt = RepeatedTimer(0.5, sample_function)
    rt.start()
    time.sleep(1)
    rt.cancel()
    current_count = counter[0]
    time.sleep(1)
    assert counter[0] == current_count


def test_repeated_timer_interval_accuracy_single_interval() -> None:
    event = Event()

    def sample_function():
        event.set()

    start_time = time.perf_counter()
    interval = 1
    rt = RepeatedTimer(interval, sample_function)
    rt.start()
    assert event.wait(2)
    end_time = time.perf_counter()
    rt.cancel()
    assert pytest.approx(end_time - start_time, rel=0.1) == interval


def test_repeated_timer_interval_accuracy_multiple_intervals() -> None:
    counter = [0]

    def sample_function():
        counter[0] += 1

    interval = 0.5
    rt = RepeatedTimer(interval, sample_function)
    rt.start()
    time.sleep(2.1)  # Let the timer run for 2.1 seconds
    rt.cancel()
    # The timer should have run 4 times, but since there might be a delay in execution, we check for at least 3 times
    assert counter[0] >= 3


def test_repeated_timer_interval_accuracy_with_pause_unpause() -> None:
    counter = {"_": 0}

    def sample_function():
        counter["_"] += 1

    interval = 1.0
    rt = RepeatedTimer(interval, sample_function, run_after=0.0)
    rt.start()
    time.sleep(0.05)  # offset slightly avoid race conditions

    time.sleep(1.0)
    assert counter["_"] == 1
    rt.pause()
    time.sleep(2.0)
    rt.unpause()
    time.sleep(1.0)
    rt.cancel()
    # The timer should have run only 2 times since we paused for 2 seconds
    assert counter["_"] == 2
