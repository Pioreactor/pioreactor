# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.dosing_automations import events
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.utils.pwm import PWM
from pioreactor.config import config


class ContinuousCycle(DosingAutomation):
    """
    Useful for using the Pioreactor as an inline sensor.
    """

    duty_cycle = 100
    hz = 100

    def run(self):
        if self.state == self.DISCONNECTED:
            # NOOP
            # we ended early.
            return

        elif self.state != self.READY:
            time.sleep(5)
            return self.run()

        else:
            event = self.execute()
            self.latest_event = event
            return event

    def on_sleeping(self):
        self.pwm.stop()

    def on_ready(self):
        self.pwm.start(self.duty_cycle)

    def on_disconnected(self):
        self.pwm.cleanup()
        super(ContinuousCycle, self).on_disconnected()

    def execute(self, *args, **kwargs):

        PIN = PWM_TO_PIN[config.getint("PWM", "media")]

        self.pwm = PWM(PIN, self.hz)
        self.pwm.start(self.duty_cycle)
        return events.RunningContinuously(
            f"Running pump on channel {config.getint('PWM', 'media')} continuously."
        )
