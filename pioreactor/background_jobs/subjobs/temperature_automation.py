# -*- coding: utf-8 -*-
import json, sys, time

from pioreactor.pubsub import QOS
from pioreactor.utils.timing import RepeatedTimer, current_utc_time
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob
from pioreactor.config import config
from pioreactor.utils.streaming_calculations import PID
from pioreactor.hardware_mappings import PWM_TO_PIN
from pioreactor.whoami import is_testing_env

if is_testing_env():
    import fake_rpi

    sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
    sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO

import RPi.GPIO as GPIO


def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))


class TemperatureAutomation(BackgroundSubJob):
    """
    This is the super class that Temperature automations inherit from. The `run` function will
    execute every `duration` minutes (selected at the start of the program). If `duration` is left
    as None, manually call `run`. This calls the `execute` function, which is what subclasses will define.

    To change setting over MQTT:

    `pioreactor/<unit>/<experiment>/led_automation/<setting>/set` value

    """

    latest_growth_rate = None
    latest_temperature = None

    latest_settings_started_at = current_utc_time()
    latest_settings_ended_at = None
    editable_settings = ["duration", "target_temperature"]

    def __init__(
        self, unit=None, experiment=None, duration=10, skip_first_run=False, **kwargs
    ):
        super(TemperatureAutomation, self).__init__(
            job_name="temperature_automation", unit=unit, experiment=experiment
        )

        self.skip_first_run = skip_first_run

        self._pwm = self.setup_pwm()

        self.logger.info(
            f"starting {self.__class__.__name__} with {duration}s intervals, and {kwargs}."
        )
        self.set_duration(duration)
        self.start_passive_listeners()

    def set_duration(self, value):
        self.duration = float(value)
        try:
            self.timer_thread.cancel()
        except AttributeError:
            pass
        finally:
            if self.duration is not None:
                self.timer_thread = RepeatedTimer(
                    self.duration,
                    self.run,
                    job_name=self.job_name,
                    run_immediately=(not self.skip_first_run),
                ).start()

    def run(self, counter=None):
        time.sleep(2)  # wait some time for data to arrive
        if self.latest_temperature is None:
            self.logger.debug("Waiting for temperature data to arrive")

        elif self.state != self.READY:
            pass
        else:
            try:
                self.execute(counter)
            except Exception as e:
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
        return

    def execute(self, counter):
        raise NotImplementedError

    def update_heater(self, new_duty_cycle):
        new_duty_cycle = clamp(0, round(float(new_duty_cycle)), 100)
        self._pwm.ChangeDutyCycle(new_duty_cycle)

    ########## Private & internal methods

    def setup_pwm(self):
        hertz = 100
        self.pin = PWM_TO_PIN[config.getint("PWM", "heating")]

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        GPIO.output(self.pin, 0)

        pwm = GPIO.PWM(self.pin, hertz)
        pwm.start(0)
        return pwm

    def on_disconnect(self):
        self.latest_settings_ended_at = current_utc_time()
        self._send_details_to_mqtt()

        try:
            self.timer_thread.cancel()
        except AttributeError:
            pass

        for job in self.sub_jobs:
            job.set_state("disconnected")

        self._clear_mqtt_cache()

        self.update_heater(0)
        self._pwm.stop()
        GPIO.cleanup(self.pin)

    def __setattr__(self, name, value) -> None:
        super(TemperatureAutomation, self).__setattr__(name, value)
        if name in self.editable_settings and name != "state":
            self.latest_settings_ended_at = current_utc_time()
            self._send_details_to_mqtt()
            self.latest_settings_started_at = current_utc_time()
            self.latest_settings_ended_at = None

    def _set_growth_rate(self, message):
        self.previous_growth_rate = self.latest_growth_rate
        self.latest_growth_rate = float(message.payload)

    def _set_temperature(self, message):
        self.previous_temperature = self.latest_temperature
        self.latest_temperature = float(message.payload)

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
            retain=True,
        )

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self._set_growth_rate,
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/growth_rate",
        )

        self.subscribe_and_callback(
            self._set_temperature,
            f"pioreactor/{self.unit}/{self.experiment}/temperature_control/temperature",
        )


# not tested, experimental


class Silent(TemperatureAutomation):
    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)

    def execute(self, *args, **kwargs):
        return


class PIDStable(TemperatureAutomation):
    def __init__(self, target_temperature, **kwargs):
        super(PIDStable, self).__init__(**kwargs)
        self.set_target_temperature(target_temperature)

        Kp = config.getfloat("temperature_automation.pid_stable", "Kp")
        Ki = config.getfloat("temperature_automation.pid_stable", "Ki")
        Kd = config.getfloat("temperature_automation.pid_stable", "Kd")

        self.pid = PID(
            Kp,
            Ki,
            Kd,
            setpoint=self.target_temperature,
            output_limits=(0, 100),
            sample_time=None,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="temperature",
        )

    def execute(self, *args, **kwargs):
        output = self.pid.update(self.latest_temperature, dt=self.duration)
        self.update_heater(output)
        return

    def set_target_temperature(self, value):
        self.target_temperature = clamp(0, float(value), 50)
        try:
            # may not be defined yet...
            self.pid.set_setpoint(self.target_temperature)
        except AttributeError:
            pass
