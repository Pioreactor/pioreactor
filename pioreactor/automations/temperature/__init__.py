# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.temperature_automation import (
    TemperatureAutomation,
)
from pioreactor.config import config
from pioreactor.utils.streaming_calculations import PID


def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))


class Silent(TemperatureAutomation):

    key = "silent"

    def __init__(self, **kwargs):
        super(Silent, self).__init__(**kwargs)


class PIDStable(TemperatureAutomation):

    key = "pid_stable"

    def __init__(self, target_temperature, **kwargs):
        super(PIDStable, self).__init__(**kwargs)
        self.set_target_temperature(target_temperature)
        self.duty_cycle = 0
        Kp = config.getfloat("temperature_automation.pid_stable", "Kp")
        Ki = config.getfloat("temperature_automation.pid_stable", "Ki")
        Kd = config.getfloat("temperature_automation.pid_stable", "Kd")

        self.pid = PID(
            Kp,
            Ki,
            Kd,
            setpoint=self.target_temperature,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="temperature",
        )

    def execute(self):
        output = self.pid.update(self.latest_temperature, dt=10)
        self.duty_cycle += output
        self.update_heater(self.duty_cycle)
        return

    def set_target_temperature(self, value):
        if float(value) > 50:
            self.logger.warning("Values over 50℃ are not supported. Setting to 50℃.")

        self.target_temperature = clamp(0, float(value), 50)
        try:
            # may not be defined yet...
            self.pid.set_setpoint(self.target_temperature)
        except AttributeError:
            pass


class ConstantDutyCycle(TemperatureAutomation):

    key = "constant_duty_cycle"
    editable_settings = ["duty_cycle"]

    def __init__(self, duty_cycle, **kwargs):
        super(ConstantDutyCycle, self).__init__(**kwargs)
        self.set_duty_cycle(duty_cycle)

    def set_duty_cycle(self, dc):
        self.duty_cycle = float(dc)
        self.update_heater(dc)
