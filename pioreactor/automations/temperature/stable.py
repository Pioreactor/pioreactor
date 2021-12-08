# -*- coding: utf-8 -*-
from pioreactor.automations.temperature.base import TemperatureAutomation
from pioreactor.config import config
from pioreactor.utils.streaming_calculations import PID
from pioreactor.utils import clamp


class DEMA:

    initial_value = 0

    def __init__(self, alpha):
        self.alpha = alpha
        self.value = self.initial_value

    def __call__(self, input_, prev_input_):
        if prev_input_ is not None:
            self.value = (
                self.alpha * (input_ - prev_input_) + (1 - self.alpha) * self.value
            )
        return self.value


class Stable(TemperatureAutomation):
    """
    Uses a PID controller to change the DC% to match a target temperature.

    """

    automation_name = "stable"
    published_settings = {
        "target_temperature": {"datatype": "float", "unit": "℃", "settable": True}
    }

    def __init__(self, target_temperature, **kwargs):
        super(Stable, self).__init__(**kwargs)
        assert target_temperature is not None, "target_temperature must be set"
        self.target_temperature = float(target_temperature)

        self.pid = PID(
            Kp=config.getfloat("temperature_automation.stable", "Kp"),
            Ki=config.getfloat("temperature_automation.stable", "Ki"),
            Kd=config.getfloat("temperature_automation.stable", "Kd"),
            setpoint=self.target_temperature,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="temperature",
        )

        # d-term is noisy, add this.
        # self.pid.pid.add_derivative_hook(DEMA(0.60))

    def execute(self):
        while not hasattr(self, "pid"):
            pass

        output = self.pid.update(
            self.latest_temperature, dt=1
        )  # 1 represents an arbitrary unit of time. The PID values will scale such that 1 makes sense.
        self.update_heater_with_delta(output)
        self.logger.debug(f"delta={output}")
        return

    def set_target_temperature(self, value):
        if float(value) > 50:
            self.logger.warning("Values over 50℃ are not supported. Setting to 50℃.")

        target_temperature = clamp(0, float(value), 50)
        self.target_temperature = target_temperature
        self.pid.set_setpoint(self.target_temperature)

        # when set_target_temperature is executed, and we wish to update the DC to some new value,
        # it's possible that it isn't updated immediately if set during the `evaluate` routine.
        if not self.is_heater_pwm_locked():
            output = self.pid.update(
                self.latest_temperature, dt=1
            )  # 1 represents an arbitrary unit of time. The PID values will scale such that 1 makes sense.
            self.update_heater_with_delta(
                output / 2
            )  # the change occurs, on average, half way into the cycle.
