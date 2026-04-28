# -*- coding: utf-8 -*-
from threading import Timer
from time import monotonic
from typing import Any

from pioreactor import structs
from pioreactor.automations import events
from pioreactor.automations.led.base import LEDAutomationJob
from pioreactor.types import LedChannel
from pioreactor.utils.timing import current_utc_datetime


class LightDarkCycle(LEDAutomationJob):
    """
    Follows a light / dark cycle. Starts with the light phase.
    """

    automation_name: str = "light_dark_cycle"
    published_settings = {
        "light_intensity": {"datatype": "float", "settable": True, "unit": "%"},
        "light_duration_minutes": {"datatype": "float", "settable": True, "unit": "min"},
        "dark_duration_minutes": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(
        self,
        light_intensity: float | str,
        light_duration_minutes: float | str,
        dark_duration_minutes: float | str,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._cycle_started_at = current_utc_datetime()
        self._phase_timer: Timer | None = None
        self._phase_timer_expected_at: float | None = None
        self.light_active: bool = False
        self.channels: tuple[LedChannel, ...] = ("D", "C")
        self.set_light_intensity(light_intensity)
        self.light_duration_minutes = float(light_duration_minutes)
        self.dark_duration_minutes = float(dark_duration_minutes)
        self._automation_strategy_start_callback = self._start_phase_schedule

    def execute(self) -> structs.AutomationEvent | None:
        elapsed_minutes = (current_utc_datetime() - self._cycle_started_at).total_seconds() / 60
        return self.trigger_leds(elapsed_minutes)

    def trigger_leds(self, elapsed_minutes: float) -> structs.AutomationEvent | None:
        if self.light_duration_minutes <= 0:
            light_should_be_on = False
        elif self.dark_duration_minutes <= 0:
            light_should_be_on = True
        else:
            cycle_duration_minutes = self.light_duration_minutes + self.dark_duration_minutes
            light_should_be_on = (elapsed_minutes % cycle_duration_minutes) < self.light_duration_minutes

        if light_should_be_on == self.light_active:
            self.logger.debug(
                f"light_dark_cycle no LED change: elapsed={elapsed_minutes:.4f}min, "
                f"light_active={self.light_active}."
            )
            return None

        self.light_active = light_should_be_on
        intensity = self.light_intensity if light_should_be_on else 0
        for channel in self.channels:
            started_at = monotonic()
            success = self.set_led_intensity(channel, intensity)
            self.logger.debug(
                f"light_dark_cycle set_led_intensity channel={channel}, intensity={intensity}, "
                f"success={success}, duration={monotonic() - started_at:.3f}s."
            )

        action = "on" if light_should_be_on else "off"
        return events.ChangedLedIntensity(f"{elapsed_minutes:.1f}min: turned {action} LEDs.")

    def set_dark_duration_minutes(self, minutes: float) -> None:
        self.dark_duration_minutes = float(minutes)
        self._run_and_schedule_next_phase()

    def set_light_duration_minutes(self, minutes: float) -> None:
        self.light_duration_minutes = float(minutes)
        self._run_and_schedule_next_phase()

    def set_light_intensity(self, intensity: float | str) -> None:
        self.light_intensity = float(intensity)
        if self.light_active:
            for channel in self.channels:
                self.set_led_intensity(channel, self.light_intensity)

    def on_sleeping(self) -> None:
        super().on_sleeping()
        self._cancel_phase_timer()

    def on_sleeping_to_ready(self) -> None:
        super().on_sleeping_to_ready()
        self._run_and_schedule_next_phase()

    def on_disconnected(self) -> None:
        self._cancel_phase_timer()
        super().on_disconnected()

    def _start_phase_schedule(self) -> None:
        self._run_and_schedule_next_phase()

    def _run_and_schedule_next_phase(self) -> structs.AutomationEvent | None:
        callback_started_at = monotonic()
        expected_at = self._phase_timer_expected_at
        lateness = None if expected_at is None else callback_started_at - expected_at
        self._phase_timer_expected_at = None
        self.logger.debug(
            "light_dark_cycle phase callback started: "
            f"state={self.state}, timer_lateness={lateness if lateness is not None else 'n/a'}s, "
            f"elapsed={(current_utc_datetime() - self._cycle_started_at).total_seconds() / 60:.4f}min."
        )

        run_once_started_at = monotonic()
        event = self.run_once(wait_for_ready=False)
        self.logger.debug(
            "light_dark_cycle run_once finished: "
            f"duration={monotonic() - run_once_started_at:.3f}s, "
            f"event={type(event).__name__ if event is not None else None}, "
            f"light_active={self.light_active}."
        )
        self._schedule_next_phase_boundary()
        self.logger.debug(
            f"light_dark_cycle phase callback finished: duration={monotonic() - callback_started_at:.3f}s."
        )
        return event

    def _seconds_until_next_phase_boundary(self) -> float | None:
        if self.light_duration_minutes <= 0 or self.dark_duration_minutes <= 0:
            self.logger.debug(
                "light_dark_cycle not scheduling next phase boundary because one duration is non-positive: "
                f"light_duration_minutes={self.light_duration_minutes}, "
                f"dark_duration_minutes={self.dark_duration_minutes}."
            )
            return None

        elapsed_minutes = (current_utc_datetime() - self._cycle_started_at).total_seconds() / 60
        cycle_duration_minutes = self.light_duration_minutes + self.dark_duration_minutes
        position_minutes = elapsed_minutes % cycle_duration_minutes
        if position_minutes < self.light_duration_minutes:
            next_boundary_minutes = self.light_duration_minutes
        else:
            next_boundary_minutes = cycle_duration_minutes

        seconds = (next_boundary_minutes - position_minutes) * 60
        self.logger.debug(
            "light_dark_cycle next phase calculation: "
            f"elapsed={elapsed_minutes:.4f}min, position={position_minutes:.4f}min, "
            f"cycle_duration={cycle_duration_minutes:.4f}min, "
            f"next_boundary={next_boundary_minutes:.4f}min, seconds={seconds:.3f}s."
        )
        return max(seconds, 0.05)

    def _schedule_next_phase_boundary(self) -> None:
        self._cancel_phase_timer()
        seconds_until_boundary = self._seconds_until_next_phase_boundary()
        if seconds_until_boundary is None or self.state != self.READY:
            self.logger.debug(
                "light_dark_cycle not scheduling phase timer: "
                f"seconds_until_boundary={seconds_until_boundary}, state={self.state}."
            )
            return

        self._phase_timer_expected_at = monotonic() + seconds_until_boundary
        self._phase_timer = Timer(seconds_until_boundary, self._run_and_schedule_next_phase)
        self._phase_timer.daemon = True
        self._phase_timer.start()
        self.logger.debug(f"light_dark_cycle scheduled next phase timer in {seconds_until_boundary:.3f}s.")

    def _cancel_phase_timer(self) -> None:
        if self._phase_timer is not None:
            self._phase_timer.cancel()
            self._phase_timer = None
            self.logger.debug("light_dark_cycle cancelled pending phase timer.")
