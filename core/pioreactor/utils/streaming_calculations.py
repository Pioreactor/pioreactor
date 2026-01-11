# -*- coding: utf-8 -*-
from typing import Optional
from typing import TYPE_CHECKING

try:
    # previously, this was part of this library. It's moved to another library. Here for bc reasons.
    from grpredict import CultureGrowthEKF  # noqa: F401
    from grpredict import ExponentialMovingAverage  # noqa: F401
    from grpredict import ExponentialMovingStd  # noqa: F401
except ImportError:
    # leader-only doesn't have this installed.
    pass

from msgspec.json import encode as dumps

if TYPE_CHECKING:
    from pioreactor.pubsub import Client


class PID:
    def __init__(
        self,
        Kp: float,
        Ki: float,
        Kd: float,
        setpoint: float | None,
        output_limits: tuple[Optional[float], Optional[float]] = (None, None),
        sample_time: Optional[float] = None,
        unit: Optional[str] = None,
        experiment: Optional[str] = None,
        job_name: Optional[str] = None,
        target_name: Optional[str] = None,
        derivative_smoothing=0.0,
        pub_client: Optional["Client"] = None,
    ) -> None:
        # PID coefficients
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.setpoint = setpoint

        # The windup limit for integral term
        self.output_limits = output_limits

        # Smoothing factor for derivative term
        assert 0.0 <= derivative_smoothing <= 1.0
        self.derivative_smoothing = derivative_smoothing

        # State variables
        self.error_prev: Optional[float] = None
        self._last_input: Optional[float] = None
        self.error_sum = 0.0
        self.derivative_prev = 0.0

        self.unit = unit
        self.experiment = experiment
        self.target_name = target_name
        self.job_name = job_name

        if pub_client is None:
            from pioreactor.pubsub import create_client

            self._external_client = False
            self.pub_client = create_client(client_id=f"pid-{self.unit}-{self.experiment}-{self.target_name}")
        else:
            self._external_client = True
            self.pub_client = pub_client

    def reset(self) -> None:
        """
        Resets the state variables.
        """
        self.error_prev = None
        self.error_sum = 0.0
        self.derivative_prev = 0.0

    def set_setpoint(self, new_setpoint: float) -> None:
        self.setpoint = new_setpoint

    def update(self, input_: float, dt: float = 1.0) -> float:
        """
        Updates the controller's internal state with the current error and time step,
        and returns the controller output.
        """
        assert isinstance(self.setpoint, float)

        error = self.setpoint - input_
        # Update error sum with clamping for anti-windup
        self.error_sum += error * dt

        if self.output_limits[0] is not None:
            self.error_sum = max(self.error_sum, self.output_limits[0])
        if self.output_limits[1] is not None:
            self.error_sum = min(self.error_sum, self.output_limits[1])

        # Calculate error derivative with smoothing
        # derivative = ((error - self.error_prev) if self.error_prev is not None else 0) / dt
        # http://brettbeauregard.com/blog/2011/04/improving-the-beginner%e2%80%99s-pid-derivative-kick/
        derivative = -(input_ - self._last_input) / dt if self._last_input is not None else 0
        derivative = (
            1 - self.derivative_smoothing
        ) * derivative + self.derivative_smoothing * self.derivative_prev

        # Update state variables
        self.error_prev = error
        self.derivative_prev = derivative

        # Calculate PID output
        output = self.Kp * error + self.Ki * self.error_sum + self.Kd * derivative
        if self.output_limits[0] is not None:
            output = max(output, self.output_limits[0])
        if self.output_limits[1] is not None:
            output = min(output, self.output_limits[1])

        self._last_input = input_
        self._last_output = output

        self.publish_pid_stats()
        return output

    def clean_up(self):
        if not self._external_client:
            self.pub_client.loop_stop()
            self.pub_client.disconnect()

    def publish_pid_stats(self) -> None:
        # not currently being saved in database. You could by adding a table and listener to mqtt_to_db_streaming
        to_send = {
            "setpoint": self.setpoint,
            "output_limits_lb": self.output_limits[0],
            "output_limits_ub": self.output_limits[1],
            "Kd": self.Kd,
            "Ki": self.Ki,
            "Kp": self.Kp,
            "integral": self.Ki * self.error_sum,
            "proportional": self.Kp * (self.error_prev if self.error_prev is not None else 0),
            "derivative": self.Kd * self.derivative_prev,
            "latest_input": self._last_input,
            "latest_output": self._last_output,
            "job_name": self.job_name,
            "target_name": self.target_name,
        }
        self.pub_client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/pid_log/{self.target_name}", dumps(to_send)
        )
