"""Lifecycle and publication shared by OD acquisition implementations."""

from __future__ import annotations

import math
import threading
from typing import Self

from pioreactor import structs
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.utils import timing


class ODReadingJob(BackgroundJob):
    job_name = "od_reading"
    published_settings = {
        "interval": {"datatype": "float", "settable": True, "unit": "s"},
        "ods": {"datatype": "ODReadings", "settable": False},
        "od1": {"datatype": "ODReading", "settable": False},
        "od2": {"datatype": "ODReading", "settable": False},
        "od3": {"datatype": "ODReading", "settable": False},
        "od4": {"datatype": "ODReading", "settable": False},
        "source": {"datatype": "string", "settable": False},
        "signal_unit": {"datatype": "string", "settable": False},
        "acquisition": {"datatype": "string", "settable": False},
    }
    ods: structs.ODReadings | None = None
    record_from_adc_timer: timing.RepeatedTimer

    def __init__(self, unit: str, experiment: str) -> None:
        super().__init__(unit=unit, experiment=experiment)
        self.first_od_obs_time: float | None = None
        self._set_for_iterating = threading.Event()
        self.source = "photodiodes"
        self.signal_unit = "V"
        self.acquisition = "scheduled"

    def set_interval(self, interval: float | None) -> None:
        if interval is not None and (not math.isfinite(interval) or interval <= 0):
            raise ValueError("interval must be positive or None")
        self.interval = interval
        if hasattr(self, "record_from_adc_timer"):
            self.record_from_adc_timer.cancel()
        if interval is None:
            return
        if interval <= 1.0:
            self.logger.warning(
                f"Recommended to have the interval between readings be larger than 1.0 sec. Currently {interval} sec."
            )
        self.record_from_adc_timer = timing.RepeatedTimer(
            interval,
            self.record_from_adc,
            job_name=self.job_name,
            run_immediately=True,
            logger=self.logger,
        )
        if self.state == self.SLEEPING:
            self.record_from_adc_timer.pause()
        self.record_from_adc_timer.start()

    def record_from_adc(self) -> structs.ODReadings | None:
        """Read once. Historical method name retained for existing Python callers."""
        raise NotImplementedError

    def publish_readings(self, readings: structs.ODReadings) -> None:
        self.ods = readings
        for channel, reading in readings.ods.items():
            setattr(self, f"od{channel}", reading)

    def _unblock_internal_event(self) -> None:
        if self.state == self.READY:
            self._set_for_iterating.set()

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> structs.ODReadings:
        while self._set_for_iterating.wait():
            self._set_for_iterating.clear()
            if self.ods is not None:
                return self.ods
        raise StopIteration

    def on_sleeping(self) -> None:
        if hasattr(self, "record_from_adc_timer"):
            self.record_from_adc_timer.pause()

    def on_sleeping_to_ready(self) -> None:
        if hasattr(self, "record_from_adc_timer"):
            self.record_from_adc_timer.unpause()

    def on_disconnected(self) -> None:
        if hasattr(self, "record_from_adc_timer"):
            self.record_from_adc_timer.cancel()
