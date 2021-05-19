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

    I tried really hard to reuse the the function add_media - but
    it just didn't work out. The problem is add_media is a function that sleeps (and in
    continous mode, we sleep forever). This doesn't play well with threads, or
    having the ability to pause/start the pumping. Though there is _some_ duplication
    here, everything feels more comfortable.

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

    def on_disconnect(self):
        self.pwm.cleanup()
        super(ContinuousCycle, self).on_disconnected()

    def execute(self, *args, **kwargs):

        PIN = PWM_TO_PIN[config.getint("PWM", "media")]

        self.pwm = PWM(PIN, self.hz)
        self.pwm.start(self.duty_cycle)
        return events.RunningContinuously(
            f"Running pump on channel {config.getint('PWM', 'media')} continuously."
        )
