# -*- coding: utf-8 -*-
import threading
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

    Idea 2: in `execute` have a while loop that flips between add and remove
        - don't need threads
        - not very spammy

    Idea 3: set duration very small, and fire small dosing events
        - follows closest to existing dosing automation patterns.

    """

    def __init__(self, **kwargs):
        super(ContinuouslyRunning, self).__init__(**kwargs)
        self.set_duration(10000000)
        self.remove_waste_thread = threading.Thread(
            target=self.remove_waste_continuously, daemon=True
        )
        self.add_media_thread = threading.Thread(
            target=self.add_media_continuously, daemon=True
        )

    def remove_waste_continuously(self):
        # dc is slightly higher to make sure we never overflow the vessel
        remove_waste(
            duration=10000000,
            duty_cycle=70,
            source_of_event=self.job_name,
            unit=self.unit,
            experiment=self.experiment,
        )

    def add_media_continuously(self):
        add_media(
            duration=10000000,
            source_of_event=self.job_name,
            unit=self.unit,
            experiment=self.experiment,
        )

    def execute(self, *args, **kwargs) -> events.Event:
        self.remove_waste_thread.start()
        self.add_media_thread.start()
        return events.ContinuouslyDosing("Pumps will always run.")
