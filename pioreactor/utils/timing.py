# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t
from contextlib import contextmanager
from contextlib import suppress
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from threading import Event
from threading import Thread
from time import perf_counter


@contextmanager
def catchtime() -> t.Generator[t.Callable, None, None]:
    """
    A context manager that measures the elapsed time between entering and exiting the context.

    Yields:
        A function that returns the elapsed time (in seconds) since the context was entered.

    Usage:
        with catchtime() as elapsed_time:
            # some code here
        print(f"Elapsed time: {elapsed_time():.2f} seconds")

    Returns:
        A generator that yields a function.
    """
    start = perf_counter()
    yield lambda: perf_counter() - start


def to_iso_format(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def current_utc_datetime() -> datetime:
    return datetime.now(timezone.utc)


def current_utc_timestamp() -> str:
    # this is timezone aware.
    return to_iso_format(current_utc_datetime())


def current_utc_datestamp() -> str:
    return current_utc_datetime().strftime("%Y-%m-%d")


def default_datetime_for_pioreactor(delta_seconds=0) -> datetime:
    return datetime(2000, 1, 1) + timedelta(seconds=delta_seconds)


def to_datetime(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


class RepeatedTimer:
    """
    A class for repeating a function in the background exactly every N seconds.

    Parameter
    ----------

    interval: float
        the number of seconds between calls
    function: callable
        the function to call
    job_name: str, optional
        the job name that is called RepeatedTimer - will be included in logs
    run_immediately: bool
        The default behaviour is to wait `interval` seconds, and then run. Change this to True to run `func` immediately.
    run_after: float, optional
        After calling `start`, wait for `run_after` seconds, then continue as normal. This happens before `run_immediately`. Default 0.
    args, kwargs:
        additional arg and kwargs to be passed into function.


    Examples
    ---------

    >> thread = RepeatedTimer(interval, callback, callback_arg1="1", callback_arg2=2)
    >> thread.start()
    >> ...
    >> thread.cancel()
    >>

    To run a job right away (i.e. don't wait `interval` seconds), use run_immediately`

    """

    def __init__(
        self,
        interval: float,
        function: t.Callable,
        job_name: t.Optional[str] = None,
        run_immediately: bool = False,
        run_after: t.Optional[float] = None,
        args=(),
        kwargs={},
    ) -> None:
        from pioreactor.logging import create_logger

        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.logger = create_logger(
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
            self.start_time = perf_counter()
            if self.run_immediately and not self.is_paused:
                self._execute_function()
        else:
            # thread exited early
            return

        while not self.event.wait(self.time_to_next_run):
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
    def time_to_next_run(self) -> float:
        if hasattr(self, "start_time"):
            return self.interval - ((perf_counter() - self.start_time) % self.interval)
        else:
            # TODO technically this is wrong, but it fixes an edge case.
            return 0

    @property
    def time_from_previous_run(self) -> float:
        return self.interval - self.time_to_next_run

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
            # so cancelling doesn't do anything
            self.thread.join()

    def start(self) -> RepeatedTimer:
        # this is idempotent
        with suppress(RuntimeError):
            self.thread.start()
        return self

    def join(self) -> None:
        self.cancel()
