# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.automations import events
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.utils.pwm import PWM
from pioreactor.config import config
from pioreactor.utils import clamp


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
    hz = 100
    published_settings = ["duty_cycle"]

    def __init__(self, duty_cycle=100, **kwargs):
        super(ContinuousCycle, self).__init__(**kwargs)
        self.duty_cycle = duty_cycle

    def set_duty_cycle(self, new_dc):
        self.duty_cycle = clamp(0, float(new_dc), 100)
        self.pwm.change_duty_cycle(new_dc)

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
            self.logger.info(f"triggered {event}.")
            self.latest_event = event
            return event

    def on_sleeping(self):
        self.pwm.stop()

    def on_sleeping_to_ready(self):
        self.pwm.start(self.duty_cycle)

    def on_disconnect(self):
        try:
            self.pwm.cleanup()
        except AttributeError:
            pass
        super(ContinuousCycle, self).on_disconnect()

    def execute(self, *args, **kwargs):

        pin = PWM_TO_PIN[config.getint("PWM_reverse", "media")]

        self.pwm = PWM(pin, self.hz)
        self.pwm.start(self.duty_cycle)
        return events.RunningContinuously(
            f"Running pump on channel {config.getint('PWM_reverse', 'media')} continuously"
        )
