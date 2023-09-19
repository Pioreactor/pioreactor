# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import cast
from typing import Optional

from msgspec.json import decode
from msgspec.json import encode

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.automations.base import AutomationJob
from pioreactor.background_jobs.temperature_control import TemperatureController
from pioreactor.pubsub import QOS
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.timing import current_utc_datetime


class TemperatureAutomationJob(AutomationJob):
    """
    This is the super class that Temperature automations inherit from.
    The `execute` function, which is what subclasses will define, is updated every time a new temperature is recorded to MQTT.
    Temperatures are updated every 10 minutes.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/temperature_automation/<setting>/set` value

    """

    _latest_growth_rate: Optional[float] = None
    _latest_normalized_od: Optional[float] = None
    previous_normalized_od: Optional[float] = None
    previous_growth_rate: Optional[float] = None

    latest_temperature = None
    previous_temperature = None

    _latest_settings_ended_at = None
    automation_name = "temperature_automation_base"  # is overwritten in subclasses
    job_name = "temperature_automation"
    published_settings: dict[str, pt.PublishableSetting] = dict()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of TemperatureAutomationJob back to TemperatureController, so the subclass
        # can be invoked in TemperatureController.
        if (
            hasattr(cls, "automation_name")
            and getattr(cls, "automation_name") != "temperature_automation_base"
        ):
            TemperatureController.available_automations[cls.automation_name] = cls

    def __init__(
        self,
        unit: str,
        experiment: str,
        temperature_control_parent: TemperatureController,
        **kwargs,
    ) -> None:
        super(TemperatureAutomationJob, self).__init__(unit, experiment)

        self.latest_normalized_od_at: datetime = current_utc_datetime()
        self.latest_growth_rate_at: datetime = current_utc_datetime()
        self.latest_temperture_at: datetime = current_utc_datetime()
        self._latest_settings_started_at = current_utc_datetime()

        self.temperature_control_parent = temperature_control_parent

    def update_heater(self, new_duty_cycle: float) -> bool:
        """
        Update heater's duty cycle. This function checks for a lock on the PWM, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """
        return self.temperature_control_parent.update_heater(new_duty_cycle)

    @property
    def heater_duty_cycle(self) -> float:
        if self.temperature_control_parent is not None:
            return self.temperature_control_parent.heater_duty_cycle
        else:
            return 0

    @heater_duty_cycle.setter
    def heater_duty_cycle(self, new_duty_cycle: float):
        return self.update_heater(new_duty_cycle)

    def is_heater_pwm_locked(self) -> bool:
        """
        Check if the heater PWM channels is locked
        """
        return self.temperature_control_parent.pwm.is_locked()

    def update_heater_with_delta(self, delta_duty_cycle: float) -> bool:
        """
        Update heater's duty cycle by value `delta_duty_cycle`. This function checks for a lock on the PWM, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """
        return self.temperature_control_parent.update_heater_with_delta(delta_duty_cycle)

    @property
    def most_stale_time(self) -> datetime:
        return min(self.latest_normalized_od_at, self.latest_growth_rate_at)

    @property
    def latest_growth_rate(self) -> float:
        # check if None
        if self._latest_growth_rate is None:
            # this should really only happen on the initialization.
            self.logger.debug("Waiting for OD and growth rate data to arrive")
            if not all(is_pio_job_running(["od_reading", "growth_rate_calculating"])):
                raise exc.JobRequiredError(
                    "`od_reading` and `growth_rate_calculating` should be Ready."
                )

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
                raise exc.JobRequiredError(
                    "`od_reading` and `growth_rate_calculating` should be running."
                )

        # check most stale time
        if (current_utc_datetime() - self.most_stale_time).seconds > 5 * 60:
            raise exc.JobRequiredError(
                "readings are too stale (over 5 minutes old) - are `od_reading` and `growth_rate_calculating` running?"
            )

        return cast(float, self._latest_normalized_od)

    ########## Private & internal methods

    def on_disconnected(self) -> None:
        self._latest_settings_ended_at = current_utc_datetime()
        self._send_details_to_mqtt()

    def __setattr__(self, name, value) -> None:
        super(TemperatureAutomationJob, self).__setattr__(name, value)
        if name in self.published_settings and name not in ("state", "latest_event"):
            self._latest_settings_ended_at = current_utc_datetime()
            self._send_details_to_mqtt()
            self._latest_settings_started_at, self._latest_settings_ended_at = (
                current_utc_datetime(),
                None,
            )

    def _set_growth_rate(self, message: pt.MQTTMessage) -> None:
        self.previous_growth_rate = self._latest_growth_rate
        payload = decode(message.payload, type=structs.GrowthRate)
        self._latest_growth_rate = payload.growth_rate
        self.latest_growth_rate_at = payload.timestamp

    def _set_temperature(self, message: pt.MQTTMessage) -> None:
        if not message.payload:
            return

        self._set_latest_temperature(decode(message.payload, type=structs.Temperature))
        return

    def _set_latest_temperature(self, temperature_struct: structs.Temperature) -> None:
        self.previous_temperature = self.latest_temperature
        self.latest_temperature = temperature_struct.temperature
        self.latest_temperature_at = temperature_struct.timestamp

        if self.state == self.READY or self.state == self.INIT:
            self.latest_event = self.execute()

        return

    def _set_OD(self, message: pt.MQTTMessage) -> None:
        self.previous_normalized_od = self._latest_normalized_od
        payload = decode(message.payload, type=structs.ODFiltered)
        self._latest_normalized_od = payload.od_filtered
        self.latest_normalized_od_at = payload.timestamp

    def _send_details_to_mqtt(self) -> None:
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/temperature_automation_settings",
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
                            for attr in self.published_settings
                            if attr not in ("state", "latest_event")
                        }
                    ),
                )
            ),
            qos=QOS.EXACTLY_ONCE,
        )

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self._set_growth_rate,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/growth_rate",
            allow_retained=False,
        )

        self.subscribe_and_callback(
            self._set_temperature,
            f"pioreactor/{self.unit}/{self.experiment}/temperature_control/temperature",
            allow_retained=False,  # only use fresh data from Temp Control.
        )

        self.subscribe_and_callback(
            self._set_OD,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/od_filtered",
            allow_retained=False,
        )


class TemperatureAutomationJobContrib(TemperatureAutomationJob):
    automation_name: str
