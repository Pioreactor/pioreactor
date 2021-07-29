# -*- coding: utf-8 -*-

import time, signal

import click

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.pubsub import subscribe
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.pwm import PWM
from pioreactor.utils import clamp
from pioreactor.utils import gpio_helpers

JOB_NAME = "stirring"


class Stirrer(BackgroundJob):
    """
    Parameters
    ------------


    duty_cycle: int
        Send message to "pioreactor/{unit}/{experiment}/stirring/duty_cycle/set" to change the stirring speed.

    dc_increase_between_adc_readings: bool
         listen for ADC reading events, and increasing stirring when not reading.

    """

    published_settings = {
        "duty_cycle": {"datatype": "float", "settable": True},
        "dc_increase_between_adc_readings": {"datatype": "boolean", "settable": True},
    }
    _previous_duty_cycle = None

    def __init__(
        self,
        duty_cycle,
        unit,
        experiment,
        hertz=50,
        dc_increase_between_adc_readings=False,
    ):
        super(Stirrer, self).__init__(job_name=JOB_NAME, unit=unit, experiment=experiment)

        self.logger.debug(f"Starting stirring with initial duty cycle {duty_cycle}.")
        self.pin = PWM_TO_PIN[config.getint("PWM_reverse", "stirring")]
        self.set_dc_increase_between_adc_readings(dc_increase_between_adc_readings)

        self.pwm = PWM(self.pin, hertz)
        self.pwm.lock()
        gpio_helpers.set_gpio_availability(self.pin, gpio_helpers.GPIO_UNAVAILABLE)

        self.set_duty_cycle(duty_cycle)
        self.start_stirring()

    def on_disconnect(self):

        self.stop_stirring()
        self.pwm.cleanup()

        if hasattr(self, "sneak_in_timer"):
            self.sneak_in_timer.cancel()

        gpio_helpers.set_gpio_availability(self.pin, gpio_helpers.GPIO_AVAILABLE)

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

    def set_dc_increase_between_adc_readings(self, dc_increase_between_adc_readings):
        self.dc_increase_between_adc_readings = int(dc_increase_between_adc_readings)
        if not self.dc_increase_between_adc_readings:
            self.sub_client.message_callback_remove(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time"
            )
            try:
                self.sneak_in_timer.cancel()
            except AttributeError:
                pass

        else:
            self.subscribe_and_callback(
                self.start_or_stop_sneaking,
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time",
            )

    def start_or_stop_sneaking(self, msg):
        if msg.payload:
            self.sneak_action_between_readings(0.6, 2.5)
        else:
            try:
                self.sneak_in_timer.cancel()
            except AttributeError:
                pass

    def sneak_action_between_readings(self, post_duration, pre_duration):
        """
        post_duration: how long to wait (seconds) after the ADS reading before running sneak_in
        pre_duration: duration between stopping the action and the next ADS reading
        """

        try:
            self.sneak_in_timer.cancel()
        except AttributeError:
            pass

        def sneak_in():
            if self.state != self.READY:
                return

            factor = 1.4  # this could be a config param? Once RPM is established, maybe a max is needed.
            original_dc = self.duty_cycle
            self.set_duty_cycle(factor * self.duty_cycle)
            time.sleep(ads_interval - (post_duration + pre_duration))
            self.set_duty_cycle(original_dc)

        # this could fail in the following way:
        # in the same experiment, the od_reading fails so that the ADC attributes are never
        # cleared. Later, this job starts, and it will pick up the _old_ ADC attributes.
        ads_start_time = float(
            subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time"
            ).payload
        )

        ads_interval = float(
            subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval"
            ).payload
        )

        # get interval, and confirm that the requirements are possible: post_duration + pre_duration <= ADS interval
        if ads_interval <= (post_duration + pre_duration):
            raise ValueError(
                "Your samples_per_second is too high to add in dynamic stirring."
            )

        self.sneak_in_timer = RepeatedTimer(ads_interval, sneak_in, run_immediately=False)

        time_to_next_ads_reading = ads_interval - (
            (time.time() - ads_start_time) % ads_interval
        )

        time.sleep(time_to_next_ads_reading + post_duration)
        self.sneak_in_timer.start()


def start_stirring(
    duty_cycle=0, dc_increase_between_adc_readings=False, unit=None, experiment=None
):
    unit = unit or get_unit_name()
    experiment = experiment or get_latest_experiment_name()

    stirrer = Stirrer(
        duty_cycle,
        dc_increase_between_adc_readings=dc_increase_between_adc_readings,
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
@click.option("--dc-increase-between-adc-readings", is_flag=True)
def click_stirring(duty_cycle, dc_increase_between_adc_readings):
    """
    Start the stirring of the Pioreactor.
    """
    start_stirring(
        duty_cycle=duty_cycle,
        dc_increase_between_adc_readings=dc_increase_between_adc_readings,
    )
    signal.pause()
