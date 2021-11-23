# -*- coding: utf-8 -*-

import time
from pioreactor.automations.led.base import LEDAutomation
from pioreactor.automations import events
from pioreactor.config import config


class Silent(LEDAutomation):

    automation_name = "silent"

    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def execute(self) -> events.Event:
        return events.NoEvent("no changes occur in Silent")


class TrackOD(LEDAutomation):
    """
    max_od: float
        the theoretical maximum (normalized) OD we expect to see.

    """

    automation_name = "track_od"

    def __init__(self, max_od: float, **kwargs):
        super(TrackOD, self).__init__(**kwargs)
        assert max_od is not None, "max_od should be set"
        self.max_od = max_od
        self.white_light = config.get(
            "leds", "white_light"
        )  # TODO: update to new led config.ini syntax
        self.set_led_intensity(self.white_light, 0)

    def execute(self) -> events.Event:
        if self.latest_od is not None:
            new_intensity = 100 ** (min(self.latest_od, self.max_od) / self.max_od)
            self.set_led_intensity(self.white_light, new_intensity)
            return events.ChangedLedIntensity(f"new output: {new_intensity}")
        else:
            return events.NoEvent()


class FlashUV(LEDAutomation):

    automation_name = "flash_uv"

    def __init__(self, **kwargs):
        super(FlashUV, self).__init__(**kwargs)
        self.uv_led = config.get("leds_reverse", "uv")
        self.set_led_intensity(self.uv_led, 0)

    def execute(self) -> events.Event:
        self.set_led_intensity(self.uv_led, 100)
        time.sleep(1)
        self.set_led_intensity(self.uv_led, 0)
        return events.ChangedLedIntensity("Flashed UV for 1 second")
