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

    key = "continuous_cycle"
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
        try:
            self.pwm.start(self.duty_cycle)
        except AttributeError:
            pass

    def on_disconnect(self):
        try:
            self.pwm.cleanup()
        except AttributeError:
            pass
        super(ContinuousCycle, self).on_disconnect()

    def execute(self, *args, **kwargs):

        pin = PWM_TO_PIN[config.getint("PWM", "media")]

        self.pwm = PWM(pin, self.hz)
        self.pwm.start(self.duty_cycle)
        return events.RunningContinuously(
            f"Running pump on channel {config.getint('PWM', 'media')} continuously."
        )
