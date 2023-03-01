# -*- coding: utf-8 -*-
from __future__ import annotations

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
        self.hours_online: int = -1
        self.light_active: bool = False
        self.channels: list[LedChannel] = ["D", "C"]
        self.set_light_intensity(light_intensity)
        self.light_duration_hours = float(light_duration_hours)
        self.dark_duration_hours = float(dark_duration_hours)

    def execute(self) -> events.AutomationEvent:
        self.hours_online += 1
        return self.trigger_leds(self.hours_online)

    def trigger_leds(self, hours: int) -> events.AutomationEvent:
        cycle_duration = self.light_duration_hours + self.dark_duration_hours

        if ((hours % cycle_duration) < self.light_duration_hours) and (not self.light_active):
            self.light_active = True

            for channel in self.channels:
                self.set_led_intensity(channel, self.light_intensity)

            return events.ChangedLedIntensity(f"{hours}h: turned on LEDs.")

        elif ((hours % cycle_duration) >= self.light_duration_hours) and (self.light_active):
            self.light_active = False
            for channel in self.channels:
                self.set_led_intensity(channel, 0)
            return events.ChangedLedIntensity(f"{hours}h: turned off LEDs.")

        else:
            return events.NoEvent(f"{hours}h: no change.")

    def set_dark_duration_hours(self, hours: int):
        self.dark_duration_hours = hours

        self.trigger_leds(self.hours_online)

    def set_light_duration_hours(self, hours: int):
        self.light_duration_hours = hours

        self.trigger_leds(self.hours_online)

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
        if duration != 60:
            self.logger.warning("Duration should be set to 60.")
        super().set_duration(duration)
