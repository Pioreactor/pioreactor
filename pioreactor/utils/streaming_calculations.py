# -*- coding: utf-8 -*-
from __future__ import annotations

from json import dumps
from math import sqrt
from typing import Optional

from pioreactor.pubsub import Client
from pioreactor.pubsub import create_client


class ExponentialMovingAverage:
    """
    Models the following:

    mean_n = (1 - alpha)·x + alpha·mean_{n-1}

    Ex: if alpha = 0, use latest value only.
    """

    def __init__(self, alpha: float):
        self.value: Optional[float] = None
        self.alpha = alpha

    def update(self, new_value: float) -> float:
        if self.value is None:
            self.value = new_value
        else:
            self.value = (1 - self.alpha) * new_value + self.alpha * self.value
        return self.value

    def get_latest(self) -> float:
        if self.value is None:
            raise ValueError("No values provided yet!")
        assert isinstance(self.value, float)
        return self.value

    def clear(self) -> None:
        self.value = None


class ExponentialMovingStd:
    """
    Models the following:

    var_n = (1 - alpha)·(x - mean_n)(x - mean_{n-1}) + alpha·var_{n-1}
    std_n = sqrt(var_n)

    Ex: if alpha = 0, use latest value only.
    """

    def __init__(
        self, alpha: float, ema_alpha: Optional[float] = None, initial_std_value: Optional[float] = None
    ):
        self._var_value = initial_std_value**2 if initial_std_value is not None else None
        self.value: Optional[float] = None
        self.alpha = alpha
        self.ema = ExponentialMovingAverage(ema_alpha or self.alpha)

    def update(self, new_value: float) -> Optional[float]:
        if self.ema.value is None:
            # need at least two data points for this algo
            self.ema.update(new_value)
            return None  # None

        mean_prev = self.ema.get_latest()
        self.ema.update(new_value)
        mean_curr = self.ema.get_latest()
        assert mean_prev is not None
        assert mean_curr is not None

        if self._var_value is None:
            self._var_value = (new_value - mean_curr) * (new_value - mean_prev)
        else:
            self._var_value = (1 - self.alpha) * (new_value - mean_curr) * (
                new_value - mean_prev
            ) + self.alpha * self._var_value
        self.value = sqrt(self._var_value)
        return self.value

    def get_latest(self) -> float:
        if self.value is None:
            raise ValueError("No values provided yet!")
        assert isinstance(self.value, float)
        return self.value

    def clear(self) -> None:
        self.value = None
        self._var_value = None
        self.ema.clear()


class CultureGrowthEKF:
    """
    Modified from the algorithm in
    https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0181923#pone.0181923.s007

    The idea is that each sensor will evolve as follows, using notation from the wikipedia page

    ```
    m_{1,t}, m_{2,t} are our sensor measurements (could be more, example here is for two sensors)
    Note that we normalized the raw sensor measurements by their initial values, so initially they
    "hover" around 1.0.

    m_{1,t} = g1(OD_{t-1}) + σ0B*noise   # noise here includes temperature noise, EM noise, stirring noise
    m_{2,t} = g2(OD_{t-1}) + σ0A*noise

    OD_t = OD_{t-1} * exp(r_{t-1} * Δt) + σ1*noise
    r_t = r_{t-1} + σ2*noise         => r_t = sum(sum(σ2*noise_i)

    # g1 and g2 are generic functions. Often they are the identity functions in OD,
    # but if using a 180deg sensor then it would be the inverse function, like exp(-OD)
    # they could also be functions that model saturation.

    Let X = [OD, r]

    f([OD, r], Δt) = [OD * exp(r Δt), r]
    h([OD, r], Δt) = [g1(OD), g2(OD)]   # recall: this is a function of the number of sensor, here we are using two sensors.

    jac(f) = [
        [exp(r Δt),  OD * exp(r Δt) * Δt, ],
        [0,          1,                   ],
    ]

    jac(h) = [
        [1, 0],  # because d(identity)/dOD = 1, d(identity)/dr = 0,
        [1, 0],
        ...
    ]

    ```

    Example
    ---------

        initial_state = np.array([obs.iloc[0], 0.0])
        initial_covariance = np.eye(2)
        process_noise_covariance = np.array([[0.00001, 0], [0, 1e-13]])
        observation_noise_covariance = np.array([[0.2]])
        ekf = CultureGrowthEKF(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

        ekf.update(...)
        ekf.state_


    Scaling
    ---------
    1. Because our OD measurements are non-stationary (we expect them to increase), the process covariance matrix needs
       to be scaled by an appropriate amount.

    2. Part of https://github.com/Pioreactor/pioreactor/issues/74


    Note on 180°
    -------------
    The measurement model for 180 is obs_t = exp(-(od_t - 1)), which comes from the beer lambert model:

      T = T_0 / 10**A

    T_0, in our model, is equal to the initial average signal from growth_rate_calculating,

      T_t = 10**{A_0} / 10**A_t = 10**{-(A_t - A_0)}

    Absorbance, A, is proportional to the optical density (in a certain range)

      T_t = 10**{-k(od_t - od_0)}

    10 is silly, so we use e.

      T_t = exp{-k(od_t - od_0)}

    The factor of of k just scales the deviations from the blank, and this can be incorporated into the Kalman Filter parameters

      T_t = exp{-(od_t - od_0)}

    Note the transformation that is often used with transmission:

      -log(T_t) = od_t - od_0

      Note: in our model, od_0 = 1.



    Useful Resources
    -------------------
    - https://dsp.stackexchange.com/questions/2347/how-to-understand-kalman-gain-intuitively
     > R is reflects in noise in the sensors, Q reflects how confident we are in the current state

    - https://perso.crans.org/club-krobot/doc/kalman.pdf
     > Another way of thinking about the weighting by K (Kalman Gain) is that as the measurement error covariance R approaches zero, the actual measurement, z, is “trusted” more and more,
     while the predicted measurement is trusted less and less. On the other hand, as the a priori estimate error covariance, Q, approaches zero the actual measurement, z,
     is trusted less and less, while the predicted measurement is trusted more and more
    """

    handle_outliers = True

    def __init__(
        self,
        initial_state,
        initial_covariance,
        process_noise_covariance,
        observation_noise_covariance,
        angles: list[str],
        outlier_std_threshold: float,
    ) -> None:
        import numpy as np

        initial_state = np.asarray(initial_state)

        assert initial_state.shape[0] == 2
        assert (
            initial_state.shape[0] == initial_covariance.shape[0] == initial_covariance.shape[1]
        ), f"Shapes are not correct,{initial_state.shape[0]=}, {initial_covariance.shape[0]=}, {initial_covariance.shape[1]=}"
        assert process_noise_covariance.shape == initial_covariance.shape
        assert self._is_positive_definite(process_noise_covariance)
        assert self._is_positive_definite(initial_covariance)
        assert self._is_positive_definite(observation_noise_covariance)

        self.process_noise_covariance = process_noise_covariance
        self.observation_noise_covariance = observation_noise_covariance
        self.state_ = initial_state
        self.covariance_ = initial_covariance
        self.n_sensors = observation_noise_covariance.shape[0]
        self.n_states = initial_state.shape[0]
        self.angles = angles
        self.outlier_std_threshold = outlier_std_threshold

        self.ems = ExponentialMovingStd(
            0.975, 0.90, initial_std_value=np.sqrt(observation_noise_covariance[0][0])
        )

    def update(self, observation_: list[float], dt: float, recent_dilution=False):
        import numpy as np

        observation = np.asarray(observation_)
        assert observation.shape[0] == self.n_sensors, (observation, self.n_sensors)

        # Predict
        state_prediction = self.update_state_from_previous_state(self.state_, dt)

        covariance_prediction = self.update_covariance_from_old_covariance(
            self.state_, self.covariance_, dt, recent_dilution=recent_dilution
        )

        # Update
        ### innovation
        residual_state = observation - self.update_observations_from_state(state_prediction)

        H = self._J_update_observations_from_state(state_prediction)

        # outlier test
        huber_threshold = self.outlier_std_threshold * (self.ems.value or 10_000)
        currently_is_outlier = abs(residual_state[0]) > huber_threshold

        if recent_dilution:
            covariance_prediction[0, 1] = 0.0
            covariance_prediction[1, 0] = 0.0
        elif self.handle_outliers and (currently_is_outlier):
            covariance_prediction[0, 0] = 2 * covariance_prediction[0, 0]
        else:
            self.ems.update(residual_state[0])

        ### optimal gain
        residual_covariance = (
            # see Scaling note above for why we multiple by state_[0]
            H @ covariance_prediction @ H.T
            + state_prediction[0] * self.observation_noise_covariance
        )

        kalman_gain_ = np.linalg.solve(residual_covariance.T, (H @ covariance_prediction.T)).T

        if self.handle_outliers and (currently_is_outlier):
            # adjust the gain s.t. we freeze gr, and scale the nOD inversely by the size of the outlier.
            kalman_gain_[0, 0] *= huber_threshold / max(abs(residual_state[0]), 1e-20)
            kalman_gain_[1:, 0] = 0

        ### update estimates
        state_ = state_prediction + kalman_gain_ @ residual_state
        covariance_ = (np.eye(self.n_states) - kalman_gain_ @ H) @ covariance_prediction

        if np.isnan(state_).any():
            raise ValueError("NaNs detected after calculation.")

        self.state_ = state_
        self.covariance_ = covariance_

        return self.state_, self.covariance_

    def update_state_from_previous_state(self, state, dt: float):
        """
        Denoted "f" in literature, x_{k} = f(x_{k-1})

        state = [OD, r]

        OD_t = OD_{t-1}·exp(r_{t-1}·Δt)
        r_t  = r_{t-1}

        """
        import numpy as np

        od, rate = state
        return np.array([od * np.exp(rate * dt), rate])

    def _J_update_observations_from_state(self, state_prediction):
        """
        Jacobian of observations model, encoded as update_observations_from_state

        measurement model is:

        m_{1,t} = g1(OD_{t-1})
        m_{2,t} = g2(OD_{t-1})
        ...

        gi are generic functions. Often they are the identity function, but if using a 180deg sensor
        then it would be the inverse function. One day it could model saturation, too.

        jac(h) = [
            [1, 0, 0],
            [1, 0, 0],
            ...
        ]

        """
        from numpy import exp
        from numpy import zeros

        od = state_prediction[0]
        J = zeros((self.n_sensors, 2))
        for i in range(self.n_sensors):
            angle = self.angles[i]
            J[i, 0] = 1.0 if (angle != "180") else -exp(-(od - 1))
        return J

    def update_covariance_from_old_covariance(self, state, covariance, dt: float, recent_dilution: bool):
        Q = self.process_noise_covariance.copy().astype(float)
        if recent_dilution:
            jump_var = max(1e-12, 0.25 * state[0] ** 2)  # keep strictly >0 for Cholesky safety
            Q[0, 0] += jump_var
        jacobian = self._J_update_state_from_previous_state(state, dt)
        return jacobian @ covariance @ jacobian.T + Q

    def update_observations_from_state(self, state_predictions):
        """
        "h" in the literature, z_k = h(x_k).

        Return shape is (n_sensors,)
        """
        import numpy as np

        obs = np.zeros((self.n_sensors,))
        od = state_predictions[0]

        for i in range(self.n_sensors):
            angle = self.angles[i]
            obs[i] = od if (angle != "180") else np.exp(-(od - 1))
        return obs

    def _J_update_state_from_previous_state(self, state, dt: float):
        """
        The prediction process is (encoded in update_state_from_previous_state)

            state = [OD, r, a]

            OD_t = OD_{t-1} * exp(r_{t-1} * Δt)
            r_t = r_{t-1}

        So jacobian should look like:

        [
            [exp(r Δt),  OD * exp(r Δt) * Δt, ],
            [0,          1,                   ],
        ]


        """
        import numpy as np

        J = np.zeros((2, 2))

        od, rate = state
        J[0, 0] = np.exp(rate * dt)
        J[1, 1] = 1

        J[0, 1] = od * np.exp(rate * dt) * dt

        return J

    @staticmethod
    def _is_positive_definite(A) -> bool:
        import numpy as np

        if np.array_equal(A, A.T):
            try:
                return True
            except np.linalg.LinAlgError:
                return False
        else:
            return False


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
        pub_client: Optional[Client] = None,
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
