# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.dosing_automations import events
from pioreactor.actions.add_media import add_media
from pioreactor.actions.remove_waste import remove_waste
from pioreactor.pubsub import subscribe


class ContinuousCycle(DosingAutomation):
    """
    Useful for using the Pioreactor as an inline sensor.

    Idea 1: I start add and remove in threads
        - only fires dosing_events once
        - UI dosing doesn't update well

        - this failed because the threads weren't exiting properly (since there was a sleep in them)

    Idea 2: in `execute` have a while loop that flips between add and remove
        - don't need threads
        - not very spammy

        this failed because the timer thread wasn't exiting properly (since it was a while loop)

    ✅ Idea 3: set duration very small, and fire small dosing events
        - follows closest to existing dosing automation patterns.



    TODO: this is a good example of waiting to execute between the ADS readings.
    """

    def __init__(self, volume=None, **kwargs):
        super(ContinuousCycle, self).__init__(**kwargs)
        self.volume = volume
        self.ads_start_time = float(
            subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time"
            ).payload
        )
        self.ads_interval = float(
            subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval"
            ).payload
        )

    def execute(self, *args, **kwargs) -> events.Event:

        # we will wait until the _next_ ads reading - so the duration should be atleast twice the ADS reading interval
        time_to_next_ads_reading = self.ads_interval - (
            (time.time() - self.ads_start_time) % self.ads_interval
        )
        time.sleep(time_to_next_ads_reading + 0.5)  # add a small buffer

        add_media(
            ml=self.volume,
            source_of_event=f"{self.job_name}:{self.__class__.__name__}",
            unit=self.unit,
            experiment=self.experiment,
        )
        time.sleep(2)
        remove_waste(
            ml=1.1 * self.volume,  # slightly more, to avoid overflow
            source_of_event=f"{self.job_name}:{self.__class__.__name__}",
            unit=self.unit,
            experiment=self.experiment,
        )
        return events.Cycle("Pumps will always run")
