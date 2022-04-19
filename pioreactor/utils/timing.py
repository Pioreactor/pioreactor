# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextlib import suppress
from datetime import datetime
from datetime import timezone
from threading import Event
from threading import Thread
from typing import Callable
from typing import Generator
from typing import Optional


def to_datetime(timestamp: str):
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")


def to_datetime_str(datetime: datetime):
    return datetime.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@contextmanager
def catchtime() -> Generator[Callable, None, None]:
    start = time.perf_counter()
    yield lambda: time.perf_counter() - start


def current_utc_time() -> str:
    # this is timezone aware.
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def brief_pause() -> None:
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
    run_after: float
        After calling `start`, wait for `run_after` seconds, then continue as normal. This happens before `run_immediately`.
    args, kwargs:
        additional arg and kwargs to be passed into function.


    Examples
    ---------

    >> thread = RepeatedTimer(interval, callback, callback_arg1="1", callback_arg2=2)
    >> thread.start()
    >> ...
    >> thread.cancel()
    >>

    To run a job right away (i.e. don't wait interval seconds), use run_immediately`

    """

    def __init__(
        self,
        interval: float,
        function: Callable,
        job_name: Optional[str] = None,
        run_immediately: bool = False,
        run_after: Optional[float] = None,
        *args,
        **kwargs,
    ) -> None:
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.logger = logging.getLogger(
            job_name or "RepeatedTimer"
        )  # TODO: I don't think this works as expected.
        self.is_paused = False
        if run_after is not None:
            assert run_after >= 0, "run_after should be non-negative."
            self.run_after = run_after
        else:
            self.run_after = 0
        self.run_immediately = run_immediately
        self.event = Event()
        self.thread = Thread(target=self._target, daemon=True)

    def _target(self) -> None:
        """
        This function runs in a thread.

        First we wait for run_after seconds (default is 0), then we run the func immediately if requested,
        and then every N seconds after that, we run func.

        """
        if not self.event.wait(self.run_after):
            self.start_time = time.time()
            if self.run_immediately:
                self._execute_function()
        else:
            # thread exited early
            return

        while not self.event.wait(self._time):
            if self.is_paused:
                continue
            self._execute_function()

    def _execute_function(self) -> None:
        try:
            self.function(*self.args, **self.kwargs)
        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)

    @property
    def _time(self) -> float:
        return self.interval - ((time.time() - self.start_time) % self.interval)

    def pause(self) -> None:
        """
        Stop the target function from running. This does not pause the timing however,
        so when you unpause, it will pick up where it is suppose to be.
        """
        self.is_paused = True

    def unpause(self) -> None:
        """
        See `pause`
        """
        self.is_paused = False

    def cancel(self) -> None:
        self.event.set()
        with suppress(RuntimeError):
            # possible to happen if self.thread hasn't started yet,
            # so cancelling doesn't make sense.
            self.thread.join()

    def start(self) -> RepeatedTimer:
        # this is idempotent
        with suppress(RuntimeError):
            self.thread.start()
        return self

    def join(self) -> None:
        self.cancel()
