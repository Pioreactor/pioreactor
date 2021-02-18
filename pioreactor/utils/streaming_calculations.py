# -*- coding: utf-8 -*-
from json import dumps


class ExponentialMovingAverage:
    def __init__(self, alpha):
        self.value = None

    def update(self, new_value):
        assert len(self.values) == self._lookback
        if self.value is None:
            self.value = new_value
        else:
            self.value = (1 - self.alpha) * new_value + self.alpha * self.value


class ExtendedKalmanFilter:
    """
    Based on the algorithm in
    https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0181923#pone.0181923.s007

    The idea is that each sensor will evolve like:

    OD_{i, t+1} = OD_{i, t} * r_t

    for all i, t.

    This model is pretty naive (different sensors will behave / saturate differently).

    Example
    ---------

        initial_state = np.array([obs.iloc[0], 0.0])
        initial_covariance = np.eye(2)
        process_noise_covariance = np.array([[0.00001, 0], [0, 1e-13]])
        observation_noise_covariance = 0.2
        ekf = ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

        ekf.update(...)
        ekf.state_

    Tuning
    --------

    Because I had such a pain tuning this, lets talk about what worked.

    So, to start our mental model, we are estimating the following:

    p(x_t | y_t, z_t), where x_t is our unknown state vector, and y_t is our prediction, and z_t is our
    latest observation. This is a Bayesian update:

    y_t ~ Normal(F(x_{t-1}), Prediction Uncertainty + Q), where F is the dynamical system
    z_t ~ Normal(mu, R)

    First, note the covariance of y_t. If Q is large, then we are _less_ confident in our prediction. How should we pick values of
    Q? Because our model says that r_t = r_{t-1} + var, we should choose var s.t. it is the expected movement in one
    time step. Back of the envelope: in 1 hour, a rate change of 0.05 is exceptional => a 2 std. movement. => hourly std = 0.025
    => per interval std = 0.025 * 5 / 3600 => var = (0.025 * 5 / 3600) ** 2

    The paper above suggests to make the process variance of OD equal to a small number. This means we (almost) fully trust the dynamic model to tell us what
    OD is. However, this means that changes in observed OD are due to changes in rate. What happens when there is a large jump due to noise? We can apply the same
    idea above to the observation variance, R. A 0.1 jump is not unexpected, but in the tails, => 2std = 0.1 => 1std = 0.05 => ....

    Uncertainty
    ------------
    Because of the model, the lower bound on the rate estimate's variance is Q[-1, -1].



    """

    def __init__(
        self,
        initial_state,
        initial_covariance,
        process_noise_covariance,
        observation_noise_covariance,
        dt=1,
    ):
        assert (
            initial_state.shape[0]
            == initial_covariance.shape[0]
            == initial_covariance.shape[1]
        ), "Shapes are not correct"
        assert process_noise_covariance.shape == initial_covariance.shape
        assert observation_noise_covariance.shape[0] == (initial_covariance.shape[0] - 1)
        assert self._is_positive_definite(process_noise_covariance)
        assert self._is_positive_definite(initial_covariance)
        assert self._is_positive_definite(observation_noise_covariance)

        self.process_noise_covariance = process_noise_covariance
        self.observation_noise_covariance = observation_noise_covariance
        self.state_ = initial_state
        self.covariance_ = initial_covariance
        self.dim = self.state_.shape[0]
        self.dt = dt

        self._OD_scale_counter = -1
        import numpy as np

        self._original_process_noise_variance = np.diag(self.process_noise_covariance)[
            : (self.dim - 1)
        ].copy()

    def predict(self):
        return (
            self._predict_state(self.state_, self.covariance_),
            self._predict_covariance(self.state_, self.covariance_),
        )

    def update(self, observation):
        import numpy as np

        observation = np.asarray(observation)
        self.update_counters()
        assert (observation.shape[0] + 1) == self.state_.shape[0], (
            (observation.shape[0] + 1),
            self.state_.shape[0],
        )
        state_prediction, covariance_prediction = self.predict()
        residual_state = observation - state_prediction[:-1]
        H = self._jacobian_observation()
        residual_covariance = (
            H @ covariance_prediction @ H.T + self.observation_noise_covariance
        )
        kalman_gain = covariance_prediction @ H.T @ np.linalg.inv(residual_covariance)
        self.state_ = state_prediction + kalman_gain @ residual_state
        self.covariance_ = (np.eye(self.dim) - kalman_gain @ H) @ covariance_prediction
        return

    def scale_OD_variance_for_next_n_steps(self, factor, n):
        import numpy as np

        d = self.dim
        self._OD_scale_counter = n
        self.process_noise_covariance[np.arange(d - 1), np.arange(d - 1)] = (
            factor * self._original_process_noise_variance
        )

    def update_counters(self):
        import numpy as np

        if self._OD_scale_counter == 0:
            d = self.dim
            self.process_noise_covariance[
                np.arange(d - 1), np.arange(d - 1)
            ] = self._original_process_noise_variance
        self._OD_scale_counter -= 1

    def _predict_state(self, state, covariance):
        import numpy as np

        return np.array(
            [v * np.exp(state[-1] * self.dt) for v in state[:-1]] + [state[-1]]
        )

    def _predict_covariance(self, state, covariance):
        return (
            self._jacobian_process(state) @ covariance @ self._jacobian_process(state).T
            + self.process_noise_covariance
        )

    def _jacobian_process(self, state):
        import numpy as np

        """
        The prediction process is
        [
            OD_{1, t+1} = OD_{1, t} * exp(r_t ∆t)
            OD_{2, t+1} = OD_{2, t} * exp(r_t ∆t)
            ...
            r_{t+1} = r_t
        ]

        """
        d = self.dim
        J = np.zeros((d, d))

        rate = state[-1]
        ODs = state[:-1]

        J[np.arange(d - 1), np.arange(d - 1)] = np.exp(rate * self.dt)
        J[np.arange(d - 1), np.arange(1, d)] = ODs * np.exp(rate * self.dt) * self.dt
        J[-1, -1] = 1.0

        return J

    def _jacobian_observation(self):
        import numpy as np

        """
        We only observe the ODs
        """
        d = self.dim
        return np.eye(d)[: (d - 1)]

    @staticmethod
    def _is_positive_definite(A):
        import numpy as np

        if np.array_equal(A, A.T):
            try:
                return True
            except np.linalg.LinAlgError:
                return False
        else:
            return False


class PID:

    # used in dosing_control classes

    def __init__(
        self,
        Kp,
        Ki,
        Kd,
        K0=0,
        setpoint=None,
        output_limits=None,
        sample_time=None,
        unit=None,
        experiment=None,
        **kwargs,
    ):
        from simple_pid import PID as simple_PID

        self.K0 = K0
        self.pid = simple_PID(
            Kp,
            Ki,
            Kd,
            setpoint=setpoint,
            output_limits=output_limits,
            sample_time=sample_time,
            **kwargs,
        )
        self.unit = unit
        self.experiment = experiment

    def set_setpoint(self, new_setpoint):
        self.pid.setpoint = new_setpoint

    def update(self, input_, dt):
        output = self.pid(input_, dt) + self.K0
        self.publish_pid_stats()
        return output

    def publish_pid_stats(self):
        from pioreactor.pubsub import publish

        to_send = {
            "setpoint": self.pid.setpoint,
            "output_limits_lb": self.pid.output_limits[0],
            "output_limits_ub": self.pid.output_limits[1],
            "Kd": self.pid.Kd,
            "Ki": self.pid.Ki,
            "Kp": self.pid.Kp,
            "K0": self.K0,
            "integral": self.pid._integral,
            "proportional": self.pid._proportional,
            "derivative": self.pid._derivative,
            "latest_input": self.pid._last_input,
            "latest_output": self.pid._last_output,
        }
        publish(f"pioreactor/{self.unit}/{self.experiment}/pid_log", dumps(to_send))
