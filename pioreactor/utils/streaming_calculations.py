# -*- coding: utf-8 -*-
from __future__ import annotations

from json import dumps
from math import sqrt
from threading import Timer
from typing import Optional

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

    def get_latest(self) -> Optional[float]:
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

    def __init__(self, alpha: float, ema_alpha: Optional[float] = None):
        self._var_value: Optional[float] = None
        self.value: Optional[float] = None
        self.alpha = alpha
        self.ema = ExponentialMovingAverage(ema_alpha or self.alpha)

    def update(self, new_value: float) -> Optional[float]:
        if self.ema.get_latest() is None:
            # need at least two data points for this algo
            self.ema.update(new_value)
            return self.value  # None

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

    def get_latest(self) -> Optional[float]:
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
    r_t = r_{t-1} + a_{t-1} * Δt + σ2*noise         => r_t = sum(a_{i}) + sum(σ2*noise_i)
    a_t = a_{t-1} + σ3*noise

    # g1 and g2 are generic functions. Often they are the identity functions in OD,
    # but if using a 180deg sensor then it would be the inverse function, like exp(-OD)
    # they could also be functions that model saturation.

    Let X = [OD, r, a]

    f([OD, r, a], Δt) = [OD * exp(r Δt), r + a Δt, a]
    h([OD, r, a], Δt) = [g1(OD), g2(OD)]   # recall: this is a function of the number of sensor, here we are using two sensors.

    jac(f) = [
        [exp(r Δt),  OD * exp(r Δt) * Δt,  0],
        [0,          1,                    Δt],
        [0,          0,                    1],
    ]

    jac(h) = [
        [1, 0, 0],  # because d(identity)/dOD = 1, d(identity)/dr = 0, d(identity)/da = 0,
        [1, 0, 0],
        ...
    ]

    ```

    Example
    ---------

        initial_state = np.array([obs.iloc[0], 0.0])
        initial_covariance = np.eye(2)
        process_noise_covariance = np.array([[0.00001, 0], [0, 1e-13]])
        observation_noise_covariance = 0.2
        ekf = CultureGrowthEKF(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

        ekf.update(...)
        ekf.state_


    Scaling
    ---------
    1. Because our OD measurements are non-stationary (we expect them to increase), the process covariance matrix needs
       to be scaled by an appropriate amount.

    2. Part of https://github.com/Pioreactor/pioreactor/issues/74


    Tuning
    --------

    *Note*: the below didn't work, I just trial-and-error it

    Because I had such a pain tuning this, lets talk about what worked.

    So, to start our mental model, we are estimating the following:

    p(x_t | y_t, z_t), where x_t is our unknown state vector, and y_t is our prediction, and z_t is our
    latest observation. This is a Bayesian update:

    y_t ~ Normal( F(x_{t-1}), Prediction Uncertainty + Q), where F is the dynamical system
    z_t ~ Normal(mu, R)

    First, note the covariance of y_t. If Q is large, then we are _less_ confident in our prediction. How should we pick values of
    Q? Because our model says that r_t = r_{t-1} + var, we should choose var s.t. it is the expected movement in one
    time step. Back of the envelope: in 1 hour, a rate change of 0.05 is exceptional => a 2 std. movement.
    => hourly std = 0.025
    => per observation-interval std =  0.025 * (5 / 3600)
    => per observation-interval var = (0.025 * (5 / 3600)) ** 2

    The paper above suggests to make the process variance of OD equal to a small number. This means we (almost) fully trust the dynamic model to tell us what
    OD is. However, this means that changes in observed OD are due to changes in rate. What happens when there is a large jump due to noise? We can apply the same
    idea above to the observation variance, R. A 0.1 jump is not unexpected, but in the tails, => 2std = 0.1 => 1std = 0.05 => ....


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

    def __init__(
        self,
        initial_state,
        initial_covariance,
        process_noise_covariance,
        observation_noise_covariance,
        angles: list[str],
    ) -> None:
        import numpy as np

        initial_state = np.asarray(initial_state)

        assert initial_state.shape[0] == 3
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

        self._currently_scaling_covariance = False
        self._currently_scaling_process_covariance = False
        self._scale_covariance_timer: Optional[Timer] = None
        self._covariance_pre_scale = None

    def update(self, observation_: list[float], dt: float):
        import numpy as np

        observation = np.asarray(observation_)
        assert observation.shape[0] == self.n_sensors, (observation, self.n_sensors)

        # Predict
        state_prediction = self.update_state_from_previous_state(self.state_, dt)
        covariance_prediction = self.update_covariance_from_old_covariance(
            self.state_, self.covariance_, dt
        )

        # Update
        ### innovation
        residual_state = observation - self.update_observations_from_state(state_prediction)
        H = self._J_update_observations_from_state(state_prediction)
        residual_covariance = (
            # see Scaling note above for why we multiple by state_[0]
            H @ covariance_prediction @ H.T
            + self.state_[0] * self.observation_noise_covariance
        )

        ### optimal gain
        kalman_gain_ = np.linalg.solve(residual_covariance.T, (H @ covariance_prediction.T)).T

        ### update estimates
        self.state_ = state_prediction + kalman_gain_ @ residual_state
        self.covariance_ = (np.eye(self.n_states) - kalman_gain_ @ H) @ covariance_prediction
        return self.state_

    def scale_OD_variance_for_next_n_seconds(self, factor: float, seconds: float):
        """
        This is a bit tricky: we do some state handling here (eg: keeping track of the previous covariance matrix)
        but we will be invoking this function multiple times. So we start a Timer but cancel it
        if we invoke this function again (i.e. a new dosing event). When the Timer successfully
        executes its function, then we restore state (add back the covariance matrix.)

        TODO: this should be decoupled from the EKF class.

        """
        import numpy as np

        def reverse_scale_covariance() -> None:
            self._currently_scaling_covariance = False
            self.covariance_ = self._covariance_pre_scale
            self._covariance_pre_scale = None

        def forward_scale_covariance():
            if not self._currently_scaling_covariance:
                self._covariance_pre_scale = self.covariance_.copy()

            self._currently_scaling_covariance = True
            self.covariance_ = np.diag(self._covariance_pre_scale.diagonal())
            self.covariance_[0, 0] *= factor

        if self._currently_scaling_covariance:
            assert self._scale_covariance_timer is not None
            self._scale_covariance_timer.cancel()

        self._scale_covariance_timer = Timer(seconds, reverse_scale_covariance)
        self._scale_covariance_timer.daemon = True
        self._scale_covariance_timer.start()

        forward_scale_covariance()

    def update_state_from_previous_state(self, state, dt: float):
        """
        Denoted "f" in literature, x_{k} = f(x_{k-1})

        state = [OD, r, a]

        OD_t = OD_{t-1}·exp(r_{t-1}·Δt)
        r_t  = r_{t-1} + a_{t-1}·Δt
        a_t  = a_{t-1}

        """
        import numpy as np

        od, rate, acc = state
        return np.array([od * np.exp(rate * dt), rate + acc * dt, acc])

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
        J = zeros((self.n_sensors, 3))
        for i in range(self.n_sensors):
            angle = self.angles[i]
            J[i, 0] = 1.0 if (angle != "180") else -exp(-(od - 1))
        return J

    def update_covariance_from_old_covariance(self, state, covariance, dt: float):
        jacobian = self._J_update_state_from_previous_state(state, dt)
        return jacobian @ covariance @ jacobian.T + self.process_noise_covariance

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
            r_t = r_{t-1} + a_{t-1}Δt
            a_t = a_{t-1}

        So jacobian should look like:

        [
            [exp(r Δt),  OD * exp(r Δt) * Δt,  0],
            [0,          1,                    Δt],
            [0,          0,                    1],
        ]


        """
        import numpy as np

        J = np.zeros((3, 3))

        od, rate, acc = state
        J[0, 0] = np.exp(rate * dt)
        J[1, 1] = 1
        J[2, 2] = 1

        J[0, 1] = od * np.exp(rate * dt) * dt
        J[1, 2] = dt

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
        setpoint: float,
        output_limits: tuple[Optional[float], Optional[float]] = (None, None),
        sample_time: Optional[float] = None,
        unit: Optional[str] = None,
        experiment: Optional[str] = None,
        job_name: Optional[str] = None,
        target_name: Optional[str] = None,
        derivative_smoothing=0.0,
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
        self.client = create_client(
            client_id=f"pid-{self.unit}-{self.experiment}-{self.target_name}"
        )

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
        self.client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/pid_log/{self.target_name}", dumps(to_send)
        )
