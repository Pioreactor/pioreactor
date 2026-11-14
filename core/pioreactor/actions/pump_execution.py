# -*- coding: utf-8 -*-
import time
from threading import Event
from threading import Lock
from threading import Thread

from pioreactor.utils.pwm import PWM


class PumpRun:
    """One execution: cancellation is permanent; join surfaces any start/stop failure.

    Hardware control never publishes telemetry. Its deadline must not depend on MQTT.
    The owning pump waits for this execution before releasing its pin.
    """

    def __init__(
        self,
        pwm: PWM,
        duty_cycle: float,
        seconds: float | None,
        cancel_events: tuple[Event, ...],
    ) -> None:
        self.pwm = pwm
        self.duty_cycle = duty_cycle
        self.seconds = seconds
        self.cancel_events = cancel_events
        self.cancelled = Event()
        self.started = Event()
        self.done = Event()
        self.started_at: float | None = None
        self.stopped_at: float | None = None
        self.completed = False
        self._start_lock = Lock()
        self._error: BaseException | None = None
        self._thread = Thread(target=self.run, name=f"pump-{pwm.pin}", daemon=True)

    def start(self) -> None:
        # Output is only enabled inside this worker, after thread creation succeeds.
        self._thread.start()
        self.started.wait()
        if self.started_at is None:
            self.join()  # Surface activation failures in the caller.

    def join(self) -> None:
        # A signal can interrupt Thread.start() before the worker is alive. The
        # caller latches cancellation before joining, so that worker cannot activate.
        if self._thread.is_alive():
            self._thread.join()
        if self._error is not None:
            raise self._error

    def cancel(self) -> None:
        with self._start_lock:
            self.cancelled.set()

    def should_stop(self) -> bool:
        return (
            self.pwm.is_cleaned_up
            or self.cancelled.is_set()
            or any(event.is_set() for event in self.cancel_events)
        )

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        return max(0.0, (self.stopped_at or time.monotonic()) - self.started_at)

    def run(self) -> None:
        try:
            try:
                with self._start_lock:
                    if self.should_stop() or self.seconds == 0:
                        self.completed = self.seconds == 0
                        return
                    self.pwm.start(self.duty_cycle, serialize=False)
                    self.started_at = time.monotonic()
                    self.started.set()
                while not self.should_stop():
                    remaining = None if self.seconds is None else self.seconds - self.elapsed
                    if remaining is not None and remaining <= 0:
                        self.completed = True
                        break
                    self.cancelled.wait(0.05 if remaining is None else min(0.05, remaining))
            finally:
                self.pwm.stop(serialize=False)
        except BaseException as error:
            self._error = error
            self.completed = False
        finally:
            self.stopped_at = time.monotonic()
            self.started.set()  # Release the caller even when activation fails or is cancelled.
            self.done.set()
