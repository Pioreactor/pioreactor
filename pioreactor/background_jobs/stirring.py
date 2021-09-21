# -*- coding: utf-8 -*-

import time, signal

import click

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.utils.pwm import PWM
from pioreactor.utils import clamp
from pioreactor.utils.gpio_helpers import GPIO_states, set_gpio_availability


class Stirrer(BackgroundJob):
    """
    Parameters
    ------------


    duty_cycle: int
        Send message to "pioreactor/{unit}/{experiment}/stirring/duty_cycle/set" to change the stirring speed.

    """

    published_settings = {
        "duty_cycle": {"datatype": "float", "settable": True, "unit": "%"},
    }
    _previous_duty_cycle = None

    def __init__(
        self,
        duty_cycle,
        unit,
        experiment,
        hertz=67,
    ):
        super(Stirrer, self).__init__(
            job_name="stirring", unit=unit, experiment=experiment
        )

        self.logger.debug(f"Starting stirring with initial duty cycle {duty_cycle}%.")
        self.pin = PWM_TO_PIN[config.getint("PWM_reverse", "stirring")]

        self.pwm = PWM(self.pin, hertz)
        self.pwm.lock()
        set_gpio_availability(self.pin, GPIO_states.GPIO_UNAVAILABLE)

        self.set_duty_cycle(duty_cycle)
        self.start_stirring()

    def on_disconnect(self):

        self.stop_stirring()
        self.pwm.cleanup()

        set_gpio_availability(self.pin, GPIO_states.GPIO_AVAILABLE)

    def start_stirring(self):
        self.pwm.start(100)  # get momentum to start
        time.sleep(0.5)
        self.pwm.change_duty_cycle(self.duty_cycle)

    def stop_stirring(self):
        # if the user unpauses, we want to go back to their previous value, and not the default.
        self.set_duty_cycle(0)

    def on_ready_to_sleeping(self):
        self._previous_duty_cycle = self.duty_cycle
        self.stop_stirring()

    def on_sleeping_to_ready(self):
        self.duty_cycle = self._previous_duty_cycle
        self.start_stirring()

    def set_duty_cycle(self, value):
        self.duty_cycle = clamp(0, round(float(value), 2), 100)
        self.pwm.change_duty_cycle(self.duty_cycle)


def start_stirring(duty_cycle=0, unit=None, experiment=None) -> Stirrer:
    unit = unit or get_unit_name()
    experiment = experiment or get_latest_experiment_name()

    stirrer = Stirrer(
        duty_cycle,
        unit=unit,
        experiment=experiment,
    )
    stirrer.start_stirring()
    return stirrer


@click.command(name="stirring")
@click.option(
    "--duty-cycle",
    default=config.getint("stirring", "duty_cycle", fallback=0),
    help="set the duty cycle",
    show_default=True,
    type=click.IntRange(0, 100, clamp=True),
)
def click_stirring(duty_cycle):
    """
    Start the stirring of the Pioreactor.
    """
    start_stirring(
        duty_cycle=duty_cycle,
    )
    signal.pause()
