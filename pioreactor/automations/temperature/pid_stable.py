# -*- coding: utf-8 -*-
from pioreactor.automations.temperature.base import TemperatureAutomation
from pioreactor.config import config
from pioreactor.utils.streaming_calculations import PID
from pioreactor.utils import clamp


class PIDStable(TemperatureAutomation):

    key = "pid_stable"
    published_settings = {
        "target_temperature": {"datatype": "float", "unit": "℃", "settable": True}
    }

    def __init__(self, target_temperature, **kwargs):
        super(PIDStable, self).__init__(**kwargs)
        assert target_temperature is not None
        self.target_temperature = float(target_temperature)

        initial_duty_cycle = (
            10  # TODO: decent starting point...can be smarter in the future
        )
        self.update_heater(initial_duty_cycle)

        self.pid = PID(
            Kp=config.getfloat("temperature_automation.pid_stable", "Kp"),
            Ki=config.getfloat("temperature_automation.pid_stable", "Ki"),
            Kd=config.getfloat("temperature_automation.pid_stable", "Kd"),
            setpoint=self.target_temperature,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            output_limits=(None, 10),  # only ever increase DC by a max limit each cycle.
            target_name="temperature",
        )

    def execute(self):
        output = self.pid.update(
            self.latest_temperature, dt=1
        )  # 1 represents an arbitrary unit of time. The PID values will scale such that 1 makes sense.
        self.update_heater_with_delta(output)
        return

    def set_target_temperature(self, value):
        if float(value) > 50:
            self.logger.warning("Values over 50℃ are not supported. Setting to 50℃.")

        target_temperature = clamp(0, float(value), 50)
        self.target_temperature = target_temperature
        self.pid.set_setpoint(self.target_temperature)
