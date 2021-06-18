# -*- coding: utf-8 -*-
import json

from pioreactor.pubsub import QOS
from pioreactor.utils.timing import current_utc_time
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob
from pioreactor.background_jobs.temperature_control import TemperatureController


class TemperatureAutomation(BackgroundSubJob):
    """
    This is the super class that Temperature automations inherit from.
    The `execute` function, which is what subclasses will define, is updated every time a new temperature is recorded to MQTT.
    Temperatures are updated every 10 minutes.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/temperature_automation/<setting>/set` value

    """

    latest_growth_rate = None
    previous_growth_rate = None

    latest_temperature = None
    previous_temperature = None

    latest_settings_started_at = current_utc_time()
    latest_settings_ended_at = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # this registers all subclasses of TemperatureAutomation back to TemperatureController, so the subclass
        # can be invoked in TemperatureController.
        if hasattr(cls, "key"):
            TemperatureController.automations[cls.key] = cls
        else:
            raise KeyError("Missing required field `key` in automation")

    def __init__(self, unit=None, experiment=None, parent=None, **kwargs):
        super(TemperatureAutomation, self).__init__(
            job_name="temperature_automation", unit=unit, experiment=experiment
        )
        self.logger.info(
            f"Starting {self.__class__.__name__}"
            + (f", and {kwargs}" if kwargs else "")
            + "."
        )

        self.temperature_control_parent = parent

        self.start_passive_listeners()

    def update_heater(self, new_duty_cycle):
        """
        Update heater's duty cycle. This function checks for a lock on the PWM, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """
        return self.temperature_control_parent.update_heater(new_duty_cycle)

    def update_heater_with_delta(self, delta_duty_cycle):
        """
        Update heater's duty cycle. This function checks for a lock on the PWM, and will not
        update if the PWM is locked.

        Returns true if the update was made (eg: no lock), else returns false
        """
        return self.temperature_control_parent.update_heater_with_delta(delta_duty_cycle)

    def execute(self):
        raise NotImplementedError

    ########## Private & internal methods

    def on_disconnect(self):
        self.latest_settings_ended_at = current_utc_time()
        self._send_details_to_mqtt()

        for job in self.sub_jobs:
            job.set_state("disconnected")

        self._clear_mqtt_cache()

    def __setattr__(self, name, value) -> None:
        super(TemperatureAutomation, self).__setattr__(name, value)
        if name in self.editable_settings and name != "state":
            self.latest_settings_ended_at = current_utc_time()
            self._send_details_to_mqtt()
            self.latest_settings_started_at, self.latest_settings_ended_at = (
                current_utc_time(),
                None,
            )

    def _set_growth_rate(self, message):
        if not message.payload:
            return

        self.previous_growth_rate = self.latest_growth_rate
        self.latest_growth_rate = float(json.loads(message.payload)["growth_rate"])

    def _set_temperature(self, message):
        if not message.payload:
            return

        self.previous_temperature = self.latest_temperature
        self.latest_temperature = float(json.loads(message.payload)["temperature"])

        if self.state == self.READY:
            self.execute()

    def _clear_mqtt_cache(self):
        # From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        for attr in self.editable_settings:
            if attr == "state":
                continue
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                None,
                retain=True,
                qos=QOS.EXACTLY_ONCE,
            )

    def _send_details_to_mqtt(self):
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/temperature_automation_settings",
            json.dumps(
                {
                    "pioreactor_unit": self.unit,
                    "experiment": self.experiment,
                    "started_at": self.latest_settings_started_at,
                    "ended_at": self.latest_settings_ended_at,
                    "automation": self.__class__.__name__,
                    "settings": json.dumps(
                        {
                            attr: getattr(self, attr, None)
                            for attr in self.editable_settings
                            if attr != "state"
                        }
                    ),
                }
            ),
            qos=QOS.EXACTLY_ONCE,
        )

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self._set_growth_rate,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/growth_rate",
            allow_retained=False,
        )

        self.subscribe_and_callback(
            self._set_temperature,
            f"pioreactor/{self.unit}/{self.experiment}/temperature_control/temperature",
            allow_retained=False,
        )


class TemperatureAutomationContrib(TemperatureAutomation):
    key: str = None
