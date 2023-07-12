# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from pioreactor.automations import events
from pioreactor.automations.led.base import LEDAutomationJob
from pioreactor.types import LedChannel


class LightDarkCycle(LEDAutomationJob):
    """
    Follows as h light / h dark cycle. Starts light ON.
    """

    automation_name: str = "light_dark_cycle"
    published_settings = {
        "duration": {
            "datatype": "float",
            "settable": False,
            "unit": "min",
        },
        "light_intensity": {"datatype": "float", "settable": True, "unit": "%"},
        "light_duration_hours": {"datatype": "integer", "settable": True, "unit": "h"},
        "dark_duration_hours": {"datatype": "integer", "settable": True, "unit": "h"},
    }

    def __init__(
        self,
        light_intensity: float | str,
        light_duration_hours: int | str,
        dark_duration_hours: int | str,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.minutes_online: int = -1
        self.light_active: bool = False
        self.channels: list[LedChannel] = ["D", "C"]
        self.set_light_intensity(light_intensity)
        self.light_duration_hours = float(light_duration_hours)
        self.dark_duration_hours = float(dark_duration_hours)

        if 0 < self.light_duration_hours < 1 / 60.0 or 0 < self.dark_duration_hours < 1 / 60.0:
            # users can input 0 - that's fine and deliberate. It's when they put in 0.01 that it makes no sense.
            self.logger.error("Durations must be at least 1 minute long.")
            raise ValueError("Durations must be at least 1 minute long.")

    def execute(self) -> Optional[events.AutomationEvent]:
        # runs every minute
        self.minutes_online += 1
        return self.trigger_leds(self.minutes_online)

    def trigger_leds(self, minutes: int) -> Optional[events.AutomationEvent]:
        """
        Changes the LED state based on the current minute in the cycle.

        The light and dark periods are calculated as multiples of 60 minutes, forming a cycle.
        Based on where in this cycle the current minute falls, the light is either turned ON or OFF.

        Args:
            minutes: The current minute of the cycle.

        Returns:
            An instance of AutomationEvent, indicating that LEDs' status might have changed.
            Returns None if the LEDs' state didn't change.
        """
        cycle_duration_min = int((self.light_duration_hours + self.dark_duration_hours) * 60)

        if ((minutes % cycle_duration_min) < (self.light_duration_hours * 60)) and (
            not self.light_active
        ):
            self.light_active = True

            for channel in self.channels:
                self.set_led_intensity(channel, self.light_intensity)

            return events.ChangedLedIntensity(f"{minutes/60:.1f}h: turned on LEDs.")

        elif ((minutes % cycle_duration_min) >= (self.light_duration_hours * 60)) and (
            self.light_active
        ):
            self.light_active = False
            for channel in self.channels:
                self.set_led_intensity(channel, 0)
            return events.ChangedLedIntensity(f"{minutes/60:.1f}h: turned off LEDs.")

        else:
            return None

    def set_dark_duration_hours(self, hours: int):
        self.dark_duration_hours = hours

        self.trigger_leds(self.minutes_online)

    def set_light_duration_hours(self, hours: int):
        self.light_duration_hours = hours

        self.trigger_leds(self.minutes_online)

    def set_light_intensity(self, intensity: float | str):
        # this is the settr of light_intensity attribute, eg. called when updated over MQTT
        self.light_intensity = float(intensity)
        if self.light_active:
            # update now!
            for channel in self.channels:
                self.set_led_intensity(channel, self.light_intensity)
        else:
            pass

    def set_duration(self, duration: float) -> None:
        if duration != 1:
            self.logger.warning("Duration should be set to 1.")
        super().set_duration(duration)
