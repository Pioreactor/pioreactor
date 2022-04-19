# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from contextlib import suppress
from typing import Optional

from pioreactor.automations import events
from pioreactor.automations.dosing.base import DosingAutomationJob
from pioreactor.config import config
from pioreactor.hardware import PWM_TO_PIN
from pioreactor.utils import clamp
from pioreactor.utils.pwm import PWM


class ContinuousCycle(DosingAutomationJob):
    """
    Useful for using the Pioreactor as an inline sensor.

    I tried really hard to reuse the the function add_media - but
    it just didn't work out. The problem is add_media is a function that sleeps (and in
    continous mode, we sleep forever). This doesn't play well with threads, or
    having the ability to pause/start the pumping. Though there is _some_ duplication
    here, everything feels more comfortable.

    """

    automation_name = "continuous_cycle"
    published_settings = {
        "duty_cycle": {"datatype": "float", "unit": "%", "settable": True},
    }

    def __init__(self, duty_cycle: float = 100.0, hz: float = 150.0, **kwargs) -> None:
        super(ContinuousCycle, self).__init__(**kwargs)
        pin = PWM_TO_PIN[config.get("PWM_reverse", "media")]
        self.pwm = PWM(pin, hz, unit=self.unit, experiment=self.experiment)
        self.duty_cycle = duty_cycle

    def set_duty_cycle(self, new_dc: float) -> None:
        self.duty_cycle = clamp(0, new_dc, 100)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def run(self) -> Optional[events.AutomationEvent]:
        if self.state == self.DISCONNECTED:
            # NOOP
            # we ended early.
            return None

        elif self.state != self.READY:
            time.sleep(5)
            return self.run()

        else:
            event = self.execute()
            self.logger.info(str(event))
            self.latest_event = event
            return event

    def on_sleeping(self) -> None:
        self.pwm.stop()

    def on_sleeping_to_ready(self) -> None:
        self.pwm.start(self.duty_cycle)

    def on_disconnected(self) -> None:
        with suppress(AttributeError):
            self.pwm.cleanup()

        super(ContinuousCycle, self).on_disconnected()

    def execute(self) -> events.AutomationEvent:
        self.pwm.start(self.duty_cycle)
        return events.RunningContinuously(
            f"Running pump on channel {config.getint('PWM_reverse', 'media')} continuously"
        )
