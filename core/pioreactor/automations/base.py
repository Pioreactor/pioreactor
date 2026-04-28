# -*- coding: utf-8 -*-
from datetime import datetime
from threading import Lock
from threading import Thread
from time import sleep
from typing import Any
from typing import Callable

from msgspec.json import decode
from msgspec.json import encode
from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.automations import events
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.pubsub import QOS
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import RepeatedTimer

DISALLOWED_AUTOMATION_NAMES = {
    "config",
}


class AutomationJob(BackgroundJob):
    automation_name = "automation_job"
    _latest_settings_ended_at = None

    previous_normalized_od: None | float = None
    previous_growth_rate: None | float = None
    previous_od: None | dict[pt.PdChannel, float] = None
    previous_od_fused: None | float = None
    # latest_normalized_od: float  // defined as properties
    # latest_growth_rate: float  // defined as properties
    # latest_od: dict[pt.PdChannel, float]  // defined as properties
    _latest_growth_rate: None | float = None
    _latest_normalized_od: None | float = None
    _latest_od: None | dict[pt.PdChannel, float] = None
    _latest_od_fused: None | float = None

    def __init__(self, unit: pt.Unit, experiment: pt.Experiment) -> None:
        super().__init__(unit, experiment)
        if self.automation_name in DISALLOWED_AUTOMATION_NAMES:
            raise NameError(f"{self.automation_name} is not allowed.")

        self.logger.info(f"Starting {self.automation_name}.")

        self.add_to_published_settings(
            "automation_name",
            {
                "datatype": "string",
                "settable": False,
            },
        )
        self.add_to_published_settings(
            "latest_event",
            {
                "datatype": "AutomationEvent",
                "settable": False,
            },
        )
        self._publish_setting("automation_name")

        self._latest_settings_started_at = current_utc_datetime()
        self._latest_run_at: datetime | None = None
        self.latest_normalized_od_at = current_utc_datetime()
        self.latest_growth_rate_at = current_utc_datetime()
        self.latest_od_at = current_utc_datetime()
        self.latest_od_fused_at = current_utc_datetime()
        self._automation_execution_lock = Lock()
        self._automation_trigger_pending = False
        self._automation_strategy_start_callback: Callable[[], None] | None = None
        self._automation_timers: list[RepeatedTimer] = []

        self.start_passive_listeners()

    def __post__init__(self) -> None:
        super().__post__init__()
        if self._automation_strategy_start_callback is not None:
            self._automation_strategy_start_callback()

    def execute(self) -> structs.AutomationEvent | None:
        """
        Overwrite in subclass
        """
        return events.NoEvent()

    def run_once(
        self,
        timeout: float = 60.0,
        *,
        wait_for_ready: bool = True,
        allowed_states: tuple[object, ...] | None = None,
    ) -> structs.AutomationEvent | None:
        """
        Execute the automation body once, with shared state gating and event handling.
        """
        if self.state == self.DISCONNECTED:
            return None

        if not self._automation_execution_lock.acquire(blocking=False):
            return None

        try:
            if wait_for_ready:
                if not self._block_until_ready(timeout=timeout):
                    return None
            elif self.state not in (allowed_states or (self.READY,)):
                return None

            try:
                event = self.execute()
                if event:
                    self.logger.info(event.display())
            except exc.JobRequiredError as e:
                self.logger.debug(e, exc_info=True)
                self.logger.warning(e)
                event = events.ErrorOccurred(str(e))
            except Exception as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
                event = events.ErrorOccurred(str(e))

            self.latest_event = event
            self._latest_run_at = current_utc_datetime()
            return event
        finally:
            self._automation_execution_lock.release()

    def run_every(
        self,
        duration_minutes: float | str,
        *,
        skip_first_run: bool | str | int = False,
        run_after_seconds: float | None = None,
    ) -> None:
        duration_minutes = float(duration_minutes)
        self.duration = duration_minutes

        def start_periodic_timer() -> None:
            skip_first_run_bool = self._coerce_bool(skip_first_run)
            self._set_periodic_timer(
                duration_minutes,
                skip_first_run=skip_first_run_bool,
                run_after_seconds=0.0 if skip_first_run_bool else run_after_seconds,
            )

        self._automation_strategy_start_callback = start_periodic_timer

    def set_duration(self, duration: float | str) -> None:
        self.duration = float(duration)
        self._set_periodic_timer(
            self.duration,
            skip_first_run=False,
            run_after_seconds=self._seconds_until_next_periodic_run(self.duration),
        )

    def trigger_run_once_from_event(self, *, timeout: float = 5.0) -> None:
        """
        Start a non-overlapping automation execution from an MQTT callback.
        """
        if self._automation_execution_lock.locked():
            self._automation_trigger_pending = True
            return

        def runner() -> None:
            while self.state != self.DISCONNECTED:
                self.run_once(timeout=timeout, wait_for_ready=False)
                if not self._automation_trigger_pending:
                    break
                self._automation_trigger_pending = False

        Thread(target=runner, daemon=True).start()

    def on_disconnected(self) -> None:
        self.cancel_automation_timers()

    def on_sleeping(self) -> None:
        for timer in self._automation_timers:
            timer.pause()

    def on_sleeping_to_ready(self) -> None:
        for timer in self._automation_timers:
            timer.unpause()

    def cancel_automation_timers(self) -> None:
        for timer in self._automation_timers:
            timer.cancel(timeout=10)
            if timer.is_alive():
                self.logger.debug("automation timer still alive!")
        self._automation_timers = []

    @staticmethod
    def _coerce_bool(value: bool | str | int) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _set_periodic_timer(
        self,
        duration_minutes: float,
        *,
        skip_first_run: bool,
        run_after_seconds: float | None,
    ) -> None:
        self.cancel_automation_timers()
        timer = RepeatedTimer(
            duration_minutes * 60,
            self.run_once,
            job_name=self.job_name,
            run_immediately=not skip_first_run,
            run_after=run_after_seconds,
            logger=self.logger,
        ).start()
        self._automation_timers.append(timer)
        self.run_thread = timer

    def _seconds_until_next_periodic_run(self, duration_minutes: float) -> float:
        if self._latest_run_at is None:
            return 0.0

        return max(
            0.0,
            (duration_minutes * 60) - (current_utc_datetime() - self._latest_run_at).total_seconds(),
        )

    def _block_until_ready(self, timeout: float) -> bool:
        if self.state == self.DISCONNECTED:
            return False

        deadline = current_utc_datetime().timestamp() + timeout
        while self.state != self.READY:
            if self.state == self.DISCONNECTED:
                return False
            if current_utc_datetime().timestamp() >= deadline:
                self.logger.debug("Timed out waiting for READY.")
                return False
            sleep(0.5)

        return True

    def _start_general_passive_listeners(self) -> None:
        super()._start_general_passive_listeners()

        self.subscribe_and_callback(
            self._set_normalized_od,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/od_filtered",
        )
        self.subscribe_and_callback(
            self._set_growth_rate,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/growth_rate",
        )
        self.subscribe_and_callback(
            self._set_ods,
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/ods",
        )
        self.subscribe_and_callback(
            self._set_od_fused,
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/od_fused",
        )

    def _set_growth_rate(self, message: pt.MQTTMessage) -> None:
        if not message.payload:
            return

        self.previous_growth_rate = self._latest_growth_rate
        payload = decode(message.payload, type=structs.GrowthRate)
        self._latest_growth_rate = payload.growth_rate
        self.latest_growth_rate_at = payload.timestamp

    def _set_normalized_od(self, message: pt.MQTTMessage) -> None:
        if not message.payload:
            return

        self.previous_normalized_od = self._latest_normalized_od
        payload = decode(message.payload, type=structs.ODFiltered)
        self._latest_normalized_od = payload.od_filtered
        self.latest_normalized_od_at = payload.timestamp

    def _set_ods(self, message: pt.MQTTMessage) -> None:
        if not message.payload:
            return

        self.previous_od = self._latest_od
        payload = decode(message.payload, type=structs.ODReadings)
        self._latest_od: dict[pt.PdChannel, float] = {c: payload.ods[c].od for c in payload.ods}
        self.latest_od_at = payload.timestamp

    def _set_od_fused(self, message: pt.MQTTMessage) -> None:
        if not message.payload:
            return

        self.previous_od_fused = self._latest_od_fused
        payload = decode(message.payload, type=structs.ODFused)
        self._latest_od_fused = payload.od_fused
        self.latest_od_fused_at = payload.timestamp

    @property
    def latest_growth_rate(self) -> float:
        # check if None
        if self._latest_growth_rate is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not all(is_pio_job_running(["od_reading", "growth_rate_calculating"])):
                raise exc.JobRequiredError("`od_reading` and `growth_rate_calculating` should be Ready.")
            while True:
                if self._latest_growth_rate is not None:
                    break
                sleep(0.5)

        # check most stale time
        if (current_utc_datetime() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return self._latest_growth_rate

    @property
    def latest_normalized_od(self) -> float:
        # check if None
        if self._latest_normalized_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not all(is_pio_job_running(["od_reading", "growth_rate_calculating"])):
                raise exc.JobRequiredError("`od_reading` and `growth_rate_calculating` should be running.")
            while True:
                if self._latest_normalized_od is not None:
                    break
                sleep(0.5)

        # check most stale time
        if (current_utc_datetime() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return self._latest_normalized_od

    @property
    def latest_od(self) -> dict[pt.PdChannel, float]:
        # check if None
        if self._latest_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not is_pio_job_running("od_reading"):
                raise exc.JobRequiredError("`od_reading` should be Ready.")
            while True:
                if self._latest_od is not None:
                    break
                sleep(0.5)

        # check most stale time
        if (current_utc_datetime() - self.latest_od_at).seconds > 5 * 60:
            raise exc.JobRequiredError(
                f"readings are too stale (over 5 minutes old) - is `od_reading` running?. Last reading occurred at {self.latest_od_at}."
            )

        assert self._latest_od is not None
        return self._latest_od

    @property
    def latest_od_fused(self) -> float:
        # check if None
        if self._latest_od_fused is None:
            self.logger.debug("Waiting for fused OD data to arrive")
            if not is_pio_job_running("od_reading"):
                raise exc.JobRequiredError("`od_reading` should be Ready.")
            while True:
                if self._latest_od_fused is not None:
                    break
                sleep(0.5)

        # check most stale time
        if (current_utc_datetime() - self.latest_od_fused_at).seconds > 5 * 60:
            raise exc.JobRequiredError(
                f"fused readings are too stale (over 5 minutes old) - is `od_reading` running?. Last reading occurred at {self.latest_od_fused_at}."
            )

        return self._latest_od_fused

    def latest_biomass_value(
        self,
        biomass_signal: str,
        od_channel: pt.PdChannel | None = None,
    ) -> float:
        if biomass_signal == "normalized_od":
            return self.latest_normalized_od
        elif biomass_signal == "od_fused":
            return self.latest_od_fused
        elif biomass_signal == "od":
            if od_channel is None:
                raise ValueError("od_channel is required when biomass_signal is 'od'.")
            return self.latest_od[od_channel]
        else:
            raise ValueError(
                f"Unsupported biomass_signal={biomass_signal}. Use one of: normalized_od, od_fused, od."
            )

    @property
    def most_stale_time(self) -> datetime:
        return min(self.latest_normalized_od_at, self.latest_growth_rate_at, self.latest_od_at)

    def _send_details_to_mqtt(self) -> None:
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{self.job_name}_settings",
            encode(
                structs.AutomationSettings(
                    pioreactor_unit=self.unit,
                    experiment=self.experiment,
                    started_at=self._latest_settings_started_at,
                    ended_at=self._latest_settings_ended_at,
                    automation_name=self.automation_name,
                    settings=encode(
                        {
                            attr: getattr(self, attr, None)
                            for attr, metadata in self.published_settings.items()
                            if metadata["settable"]
                        }
                    ),
                )
            ),
            qos=QOS.EXACTLY_ONCE,
        )

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name in self.published_settings and name != "state" and self.published_settings[name]["settable"]:
            self._latest_settings_ended_at = current_utc_datetime()
            self._send_details_to_mqtt()
            self._latest_settings_started_at, self._latest_settings_ended_at = (
                current_utc_datetime(),
                None,
            )
