# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from time import sleep
from typing import cast

from msgspec.json import decode
from msgspec.json import encode

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.automations import events
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.pubsub import QOS
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.timing import current_utc_datetime

DISALLOWED_AUTOMATION_NAMES = {
    "config",
}


class AutomationJob(BackgroundJob):
    automation_name = "automation_job"
    _latest_settings_ended_at = None

    previous_normalized_od: None | float = None
    previous_growth_rate: None | float = None
    previous_od: None | dict[pt.PdChannel, float] = None
    # latest_normalized_od: float  // defined as properties
    # latest_growth_rate: float  // defined as properties
    # latest_od: dict[pt.PdChannel, float]  // defined as properties
    _latest_growth_rate: None | float = None
    _latest_normalized_od: None | float = None
    _latest_od: None | dict[pt.PdChannel, float] = None

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
        self.latest_normalized_od_at = current_utc_datetime()
        self.latest_growth_rate_at = current_utc_datetime()
        self.latest_od_at = current_utc_datetime()

        self.start_passive_listeners()

    def execute(self) -> events.AutomationEvent | None:
        """
        Overwrite in subclass
        """
        return events.NoEvent()

    def _start_general_passive_listeners(self) -> None:
        super()._start_general_passive_listeners()

        self.subscribe_and_callback(
            self._set_normalized_od,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/od_filtered",
        )
        self.subscribe_and_callback(
            self._set_growth_rate,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/growth_rate",
        )
        self.subscribe_and_callback(
            self._set_ods,
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/ods",
        )

    def _set_growth_rate(self, message: pt.MQTTMessage) -> None:
        if not message.payload:
            return

        self.previous_growth_rate = self._latest_growth_rate
        payload = decode(message.payload, type=structs.GrowthRate)
        self._latest_growth_rate = payload.growth_rate
        self.latest_growth_rate_at = payload.timestamp

    def _set_normalized_od(self, message: pt.MQTTMessage) -> None:
        if not message.payload:
            return

        self.previous_normalized_od = self._latest_normalized_od
        payload = decode(message.payload, type=structs.ODFiltered)
        self._latest_normalized_od = payload.od_filtered
        self.latest_normalized_od_at = payload.timestamp

    def _set_ods(self, message: pt.MQTTMessage) -> None:
        if not message.payload:
            return

        self.previous_od = self._latest_od
        payload = decode(message.payload, type=structs.ODReadings)
        self._latest_od: dict[pt.PdChannel, float] = {c: payload.ods[c].od for c in payload.ods}
        self.latest_od_at = payload.timestamp

    @property
    def latest_growth_rate(self) -> float:
        # check if None
        if self._latest_growth_rate is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not all(is_pio_job_running(["od_reading", "growth_rate_calculating"])):
                raise exc.JobRequiredError("`od_reading` and `growth_rate_calculating` should be Ready.")
            while True:
                if self._latest_growth_rate is not None:
                    break
                sleep(0.5)

        # check most stale time
        if (current_utc_datetime() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_growth_rate)

    @property
    def latest_normalized_od(self) -> float:
        # check if None
        if self._latest_normalized_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not all(is_pio_job_running(["od_reading", "growth_rate_calculating"])):
                raise exc.JobRequiredError("`od_reading` and `growth_rate_calculating` should be running.")
            while True:
                if self._latest_normalized_od is not None:
                    break
                sleep(0.5)

        # check most stale time
        if (current_utc_datetime() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_normalized_od)

    @property
    def latest_od(self) -> dict[pt.PdChannel, float]:
        # check if None
        if self._latest_od is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not is_pio_job_running("od_reading"):
                raise exc.JobRequiredError("`od_reading` should be Ready.")
            while True:
                if self._latest_od is not None:
                    break
                sleep(0.5)

        # check most stale time
        if (current_utc_datetime() - self.latest_od_at).seconds > 5 * 60:
            raise exc.JobRequiredError(
                f"readings are too stale (over 5 minutes old) - is `od_reading` running?. Last reading occurred at {self.latest_od_at}."
            )

        assert self._latest_od is not None
        return self._latest_od

    @property
    def most_stale_time(self) -> datetime:
        return min(self.latest_normalized_od_at, self.latest_growth_rate_at, self.latest_od_at)

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
