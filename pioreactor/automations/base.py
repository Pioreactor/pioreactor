# -*- coding: utf-8 -*-
from __future__ import annotations

from msgspec.json import encode

from pioreactor import structs
from pioreactor.automations import events
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.pubsub import QOS
from pioreactor.utils.timing import current_utc_datetime


DISALLOWED_AUTOMATION_NAMES = {
    "config",
}


class AutomationJob(BackgroundJob):
    automation_name = "automation_job"
    _latest_settings_ended_at = None

    def __init__(self, unit: str, experiment: str) -> None:
        super().__init__(unit, experiment)
        if self.automation_name in DISALLOWED_AUTOMATION_NAMES:
            raise NameError(f"{self.automation_name} is not allowed.")

        self.logger.info(f"Starting {self.automation_name}.")

        self.add_to_published_settings(
            "automation_name",
            {
                "datatype": "string",
                "settable": False,
            },
        )
        self.add_to_published_settings(
            "latest_event",
            {
                "datatype": "AutomationEvent",
                "settable": False,
            },
        )
        self._publish_setting("automation_name")

        self._latest_settings_started_at = current_utc_datetime()

    def on_init_to_ready(self) -> None:
        self.start_passive_listeners()

    def execute(self) -> events.AutomationEvent | None:
        """
        Overwrite in subclass
        """
        return events.NoEvent()

    def _send_details_to_mqtt(self) -> None:
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{self.job_name}_settings",
            encode(
                structs.AutomationSettings(
                    pioreactor_unit=self.unit,
                    experiment=self.experiment,
                    started_at=self._latest_settings_started_at,
                    ended_at=self._latest_settings_ended_at,
                    automation_name=self.automation_name,
                    settings=encode(
                        {
                            attr: getattr(self, attr, None)
                            for attr, metadata in self.published_settings.items()
                            if metadata["settable"]
                        }
                    ),
                )
            ),
            qos=QOS.EXACTLY_ONCE,
        )

    def __setattr__(self, name, value) -> None:
        super().__setattr__(name, value)
        if name in self.published_settings and name != "state" and self.published_settings[name]["settable"]:
            self._latest_settings_ended_at = current_utc_datetime()
            self._send_details_to_mqtt()
            self._latest_settings_started_at, self._latest_settings_ended_at = (
                current_utc_datetime(),
                None,
            )
