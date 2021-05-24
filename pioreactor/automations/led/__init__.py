# -*- coding: utf-8 -*-

import time
from pioreactor.background_jobs.subjobs.led_automation import LEDAutomation
from pioreactor.automations import events
from pioreactor.config import config


class Silent(LEDAutomation):

    key = "silent"

    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def execute(self, *args, **kwargs) -> events.Event:
        return events.NoEvent("nothing occurs in Silent")


class TrackOD(LEDAutomation):
    """
    max_od: float
        the theoretical maximum (normalized) OD we expect to see.

    """

    key = "track_od"

    def __init__(self, max_od=None, **kwargs):
        super(TrackOD, self).__init__(**kwargs)
        assert max_od is not None, "max_od should be set"
        self.max_od = max_od
        self.white_light = config.get("leds", "white_light")
        self.set_led_intensity(self.white_light, 0)

    def execute(self, *args, **kwargs) -> events.Event:
        new_intensity = 100 ** (min(self.latest_od, self.max_od) / self.max_od)
        self.set_led_intensity(self.white_light, new_intensity)
        return events.IncreasedLuminosity(f"new output: {new_intensity}")


class FlashUV(LEDAutomation):

    key = "flash_uv"

    def __init__(self, **kwargs):
        super(FlashUV, self).__init__(**kwargs)
        self.uv_led = config.get("leds", "uv")

        self.set_led_intensity(self.uv_led, 0)

    def execute(self, *args, **kwargs) -> events.Event:
        self.set_led_intensity(self.uv_led, 100)
        time.sleep(1)
        self.set_led_intensity(self.uv_led, 0)
        return events.UvFlash("Flashed UV for 1 second")
