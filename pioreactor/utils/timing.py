# -*- coding: utf-8 -*-
import time, sys, logging
from threading import Event, Thread, Timer
from time import perf_counter
from contextlib import contextmanager


def every(delay, task, *args, **kwargs):
    """
    Executing `task` once initially, and then every `delay` seconds later.

    Yields the result back to the caller.

    from https://stackoverflow.com/questions/474528/what-is-the-best-way-to-repeatedly-execute-a-function-every-x-seconds
    """
    next_time = time.time() + delay
    counter = 0
    while True:
        try:
            counter += 1
            kwargs["counter"] = counter
            yield task(*args, **kwargs)
        except Exception as e:
            raise e
            # in production code you might want to have this instead of course:
            # logger.exception("Problem while executing repetitive task.")
        if "pytest" in sys.modules:
            time.sleep(0)
        else:
            time.sleep(max(0, next_time - time.time()))
        # skip tasks if we are behind schedule:
        next_time += (time.time() - next_time) // delay * delay + delay


@contextmanager
def catchtime() -> float:
    start = perf_counter()
    yield lambda: perf_counter() - start


class RepeatedTimer:
    """
    A class for repeating a function in the background exactly every N seconds.

    Use like:

    >>thread = RepeatedTimer(seconds_to_wait, callback)
    >>thread.start()
    >>...
    >>thread.cancel()

    To run a job right away (i.e. don't wait interval seconds), use run_immediately

    """

    def __init__(
        self, interval, function, job_name=None, run_immediately=False, *args, **kwargs
    ):
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.logger = logging.getLogger(job_name or "RepeatedTimer")

        if run_immediately:
            temp_thread = Timer(0, self.function, self.args, self.kwargs)
            temp_thread.daemon = True
            temp_thread.start()

        self.event = Event()
        self.thread = Thread(target=self._target)
        self.thread.daemon = True

    def _target(self):
        while not self.event.wait(self._time):
            self.function(*self.args, **self.kwargs)

    @property
    def _time(self):
        return self.interval - ((time.time() - self.start_time) % self.interval)

    def cancel(self):
        self.event.set()
        self.thread.join()

    def start(self):
        self.start_time = time.time()
        self.thread.start()
        return self
