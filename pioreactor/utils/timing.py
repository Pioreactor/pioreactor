# -*- coding: utf-8 -*-
import time, logging
from datetime import datetime, timezone
from threading import Event, Thread
from time import perf_counter

from pioreactor.whoami import is_testing_env

from contextlib import contextmanager


@contextmanager
def catchtime() -> float:
    start = perf_counter()
    yield lambda: perf_counter() - start


def current_utc_time():
    # this is timezone aware.
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def brief_pause():
    if is_testing_env():
        return
    else:
        time.sleep(3)
        return


class RepeatedTimer:
    """
    A class for repeating a function in the background exactly every N seconds.

    Parameter
    ----------

    interval: float
        the number of seconds between calls
    function: callable
        the function to call
    job_name: str
        the job name that is called RepeatedTimer - will be included in logs
    run_immediately: bool
        The default behaviour is to wait `interval` seconds, and then run. Change this to True to run `func` immediately.
    run_after: int
        After calling `start`, wait for `run_after` seconds, then continue as normal. This happens before `run_immediately`.
    args, kwargs:
        additional arg and kwargs to be passed into function.


    Examples
    ---------

    >> thread = RepeatedTimer(seconds_to_wait, callback)
    >> thread.start()
    >> ...
    >> thread.cancel()

    To run a job right away (i.e. don't wait interval seconds), use run_immediately

    """

    def __init__(
        self,
        interval,
        function,
        job_name=None,
        run_immediately=False,
        run_after=None,
        *args,
        **kwargs
    ):
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.logger = logging.getLogger(
            job_name or "RepeatedTimer"
        )  # TODO: I don't think this works as expected.
        self.is_paused = False
        self.run_after = run_after or 0
        self.run_immediately = run_immediately
        self.event = Event()
        self.thread = Thread(target=self._target, daemon=True)

    def _target(self):
        """
        First we wait for run_after seconds (default is 0), then we run the func immediately if requested,
        and then every N seconds after that, we run func.

        """
        self.event.wait(self.run_after)

        self.start_time = time.time()
        if self.run_immediately:
            self.function(*self.args, **self.kwargs)

        while not self.event.wait(self._time):
            if self.is_paused:
                continue
            try:
                self.function(*self.args, **self.kwargs)
            except Exception as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)

    @property
    def _time(self):
        return self.interval - ((time.time() - self.start_time) % self.interval)

    def pause(self):
        """
        Stop the target function from running. This does not pause the timing however,
        so when you unpause, it will pick up where it is suppose to be.
        """
        self.is_paused = True

    def unpause(self):
        """
        See `pause`
        """
        self.is_paused = False

    def cancel(self):
        self.event.set()
        try:
            self.thread.join()
        except RuntimeError:
            # possible to happen if self.thread hasn't started yet,
            # so cancelling doesn't make sense.
            pass

    def start(self):
        self.thread.start()
        return self

    def join(self):
        self.cancel()
