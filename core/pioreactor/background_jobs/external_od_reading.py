"""Native OD activity backed by a continuously acquiring plugin sensor."""

import math
from threading import RLock
from time import monotonic
from time import sleep

from pioreactor import structs
from pioreactor.background_jobs.od_reading_job import ODReadingJob
from pioreactor.hardware import ODHardwareConfig
from pioreactor.od_sources import create_od_source
from pioreactor.od_sources import ODSource
from pioreactor.utils.timing import current_utc_datetime


class ExternalODReader(ODReadingJob):
    def __init__(
        self, hardware: ODHardwareConfig, unit: str, experiment: str, interval: float | None
    ) -> None:
        super().__init__(unit, experiment)
        self._lock = RLock()
        self.reader: ODSource | None = None
        self.source = hardware.driver
        self.acquisition = "continuous"
        self.reader = create_od_source(hardware, self.logger)
        self.signal_unit = self.reader.signal_unit
        self.reader.start()
        self.set_interval(interval)

    def record_from_adc(self) -> structs.ODReadings | None:
        with self._lock:
            if self.reader is None or self.state in (self.SLEEPING, self.DISCONNECTED, self.LOST):
                return None
            value = self.reader.read()
            if value is None:
                return None
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"OD source returned an invalid observation: {value}")
            timestamp = current_utc_datetime()
            readings = structs.ODReadings(
                timestamp=timestamp,
                ods={
                    "1": structs.SensorODReading(
                        timestamp=timestamp,
                        od=value,
                        channel="1",
                        source=self.source,
                        signal_unit=self.signal_unit,
                    )
                },
            )
            self.publish_readings(readings)
            self._unblock_internal_event()
            return readings

    def snapshot(self, timeout: float = 60.0) -> structs.ODReadings:
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            readings = self.record_from_adc()
            if readings is not None:
                return readings
            sleep(0.1)
        raise TimeoutError("OD source did not produce a measurement within the snapshot timeout.")

    def on_sleeping(self) -> None:
        super().on_sleeping()
        with self._lock:
            if self.reader is not None:
                self.reader.stop()

    def on_sleeping_to_ready(self) -> None:
        with self._lock:
            if self.reader is not None:
                self.reader.start()
        super().on_sleeping_to_ready()

    def on_disconnected(self) -> None:
        super().on_disconnected()
        reader = getattr(self, "reader", None)
        if reader is not None:
            reader.close()
