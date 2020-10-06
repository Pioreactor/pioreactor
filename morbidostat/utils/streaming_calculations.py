# -*- coding: utf-8 -*-
from statistics import *
import json

import numpy as np
from simple_pid import PID as simple_PID

from morbidostat.utils.pubsub import publish


class MovingStats:
    def __init__(self, lookback=5):
        self.values = [None] * lookback
        self._lookback = lookback

    def update(self, new_value):
        self.values.pop(0)
        self.values.append(new_value)
        assert len(self.values) == self._lookback

    @property
    def mean(self):
        try:
            return mean(self.values)
        except:
            pass

    @property
    def std(self):
        try:
            return stdev(self.values)
        except:
            pass


class LowPassFilter:
    def __init__(self, length_of_filter, low_pass_corner_frequ, time_between_reading):
        from scipy import signal

        self._latest_reading = None
        self.filtwindow = signal.firwin(length_of_filter, low_pass_corner_frequ, fs=1 / time_between_reading)
        self.window = signal.lfilter_zi(self.filtwindow, 1)

    def update(self, value):
        from scipy import signal

        self._latest_reading, self.window = signal.lfilter(self.filtwindow, 1, [value], zi=self.window)

    @property
    def latest_reading(self):
        return self._latest_reading[0]


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

        initial_state = np.array([obs.iloc[0], 1.])
        initial_covariance = np.eye(2)
        process_noise_covariance = np.array([[0.00001, 0], [0, 1e-13]])
        observation_noise_covariance = 0.2
        ekf = ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

        ekf.update(...)
        ekf.state_

    """

    def __init__(self, initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance):
        assert initial_state.shape[0] == initial_covariance.shape[0] == initial_covariance.shape[1]
        assert process_noise_covariance.shape == initial_covariance.shape
        assert self._is_positive_definite(process_noise_covariance)
        assert self._is_positive_definite(initial_covariance)
        assert self._is_positive_definite(observation_noise_covariance)

        self._process_noise_covariance = process_noise_covariance
        self.observation_noise_covariance = observation_noise_covariance
        self.state_ = initial_state
        self.covariance_ = initial_covariance
        self.dim = self.state_.shape[0]

        self._OD_scale_counter = -1
        self._rate_scale_counter = -1

        self._original_process_noise_variance = np.diag(self._process_noise_covariance)[: (self.dim - 1)].copy()
        self._original_rate_noise_variance = self._process_noise_covariance[-1, -1]

    def predict(self):
        return (self._predict_state(self.state_, self.covariance_), self._predict_covariance(self.state_, self.covariance_))

    def update(self, observation):
        # TODO: incorporate delta_time
        assert observation.shape[0] + 1 == self.state_.shape[0]
        state_prediction, covariance_prediction = self.predict()
        residual_state = observation - state_prediction[:-1]
        H = self._jacobian_observation()
        residual_covariance = H @ covariance_prediction @ H.T + self.observation_noise_covariance
        kalman_gain = covariance_prediction @ H.T @ np.linalg.inv(residual_covariance)
        self.state_ = state_prediction + kalman_gain @ residual_state
        self.covariance_ = (np.eye(self.dim) - kalman_gain @ H) @ covariance_prediction
        return

    def scale_OD_variance_for_next_n_steps(self, factor, n):
        d = self.dim
        self._OD_scale_counter = n
        self._process_noise_covariance[np.arange(d - 1), np.arange(d - 1)] = factor * self._original_process_noise_variance

    def scale_rate_variance_for_next_n_steps(self, factor, n):
        d = self.dim
        self._rate_scale_counter = n
        self._process_noise_covariance[-1, -1] = factor * self._original_rate_noise_variance

    def process_noise_covariance(self):
        if self._OD_scale_counter == 0:
            d = self.dim
            self._process_noise_covariance[np.arange(d - 1), np.arange(d - 1)] = self._original_process_noise_variance
        self._OD_scale_counter -= 1

        if self._rate_scale_counter == 0:
            self._process_noise_covariance[-1, -1] = self._original_rate_noise_variance
        self._rate_scale_counter -= 1
        return self._process_noise_covariance

    def _predict_state(self, state, covariance):
        return np.array([v * state[-1] for v in state[:-1]] + [state[-1]])

    def _predict_covariance(self, state, covariance):
        return self._jacobian_process(state) @ covariance @ self._jacobian_process(state).T + self.process_noise_covariance()

    def _jacobian_process(self, state):
        """
        The prediction process is
        [
            OD_{1, t+1} = OD_{1, t} * r_t
            OD_{2, t+1} = OD_{2, t} * r_t
            ...
            r_{t+1} = r_t

        ]

        """
        d = self.dim
        J = np.zeros((d, d))

        rate = state[-1]
        ODs = state[:-1]

        J[np.arange(d - 1), np.arange(d - 1)] = rate
        J[np.arange(d - 1), np.arange(1, d)] = ODs
        J[-1, -1] = 1.0

        return J

    def _jacobian_observation(self):
        """
        We only observe the ODs
        """
        d = self.dim
        return np.eye(d)[: (d - 1)]

    @staticmethod
    def _is_positive_definite(A):
        if np.array_equal(A, A.T):
            try:
                return True
            except np.linalg.LinAlgError:
                return False
        else:
            return False


class PID:
    # used in io_controlling classes

    def __init__(self, *args, unit=None, experiment=None, verbose=False, **kwargs):
        self.pid = simple_PID(*args, **kwargs)
        self.unit = unit
        self.experiment = experiment
        self.verbose = verbose

    def update(self, input_, dt=None):
        output = self.pid(input_, dt)
        self.publish_pid_stats()
        return output

    def publish_pid_stats(self):
        to_send = {
            "setpoint": self.pid.setpoint,
            "output_limits_lb": self.pid.output_limits[0],
            "output_limits_ub": self.pid.output_limits[1],
            "Kd": self.pid.Kd,
            "Ki": self.pid.Ki,
            "Kp": self.pid.Kp,
            "integral": self.pid._integral,
            "proportional": self.pid._proportional,
            "derivative": self.pid._derivative,
            "latest_input": self.pid._last_input,
            "latest_output": self.pid._last_output,
        }
        publish(f"morbidostat/{self.unit}/{self.experiment}/pid_log", json.dumps(to_send), verbose=self.verbose)
