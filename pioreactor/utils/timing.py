# -*- coding: utf-8 -*-
import time, logging
from datetime import datetime
from threading import Event, Thread, Timer
from time import perf_counter
from contextlib import contextmanager
from pioreactor.whoami import is_testing_env


def current_utc_time():
    return datetime.utcnow().isoformat()


def brief_pause():
    if is_testing_env():
        return
    else:
        time.sleep(3)
        return


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

        # TODO: should these lines actually go in .start() method? That makes more sense.
        if run_immediately:
            temp_thread = Timer(0, self.function, self.args, self.kwargs)
            temp_thread.daemon = True
            temp_thread.start()

        self.event = Event()
        self.thread = Thread(target=self._target, daemon=True)

    def _target(self):
        while not self.event.wait(self._time):
            try:
                self.function(*self.args, **self.kwargs)
            except Exception as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)

    @property
    def _time(self):
        return self.interval - ((time.time() - self.start_time) % self.interval)

    def cancel(self):
        self.event.set()
        try:
            self.thread.join()
        except RuntimeError:
            # possible to happen if self.thread hasn't started yet,
            # so cancelling doesn't make sense.
            pass

    def start(self):
        self.start_time = time.time()
        self.thread.start()
        return self

    def join(self):
        self.cancel()
