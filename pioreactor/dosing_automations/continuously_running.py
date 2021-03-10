# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.dosing_automations import events
from pioreactor.actions.add_media import add_media
from pioreactor.actions.remove_waste import remove_waste


class ContinuouslyRunning(DosingAutomation):
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

    """

    def __init__(self, volume=None, **kwargs):
        super(ContinuouslyRunning, self).__init__(**kwargs)
        self.volume = volume

    def execute(self, *args, **kwargs) -> events.Event:
        add_media(
            ml=self.volume,
            source_of_event=f"{self.job_name}:{self.__class__.__name__}",
            unit=self.unit,
            experiment=self.experiment,
        )
        time.sleep(3)
        remove_waste(
            ml=1.1 * self.volume,  # slightly more, to avoid overflow
            source_of_event=f"{self.job_name}:{self.__class__.__name__}",
            unit=self.unit,
            experiment=self.experiment,
        )
        return events.ContinuouslyDosing("Pumps will always run")
