import numpy as np
from statistics import *
from collections import namedtuple


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

    def __init__(
        self, initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance,
    ):
        assert initial_state.shape[0] == initial_covariance.shape[0] == initial_covariance.shape[1]
        assert process_noise_covariance.shape == initial_covariance.shape

        self._process_noise_covariance = process_noise_covariance
        self.observation_noise_covariance = observation_noise_covariance
        self.state_ = initial_state
        self.covariance_ = initial_covariance

        self._counter = -1
        self._original_process_noise_variance = self._process_noise_covariance[0, 0]

    def predict(self):
        return (
            self._predict_state(self.state_, self.covariance_),
            self._predict_covariance(self.state_, self.covariance_),
        )

    def update(self, observation, delta_time=1):
        # TODO: incorporate delta_time
        state_prediction, covariance_prediction = self.predict()
        residual_state = observation - state_prediction[:-1]
        H = self._jacobian_observation()
        residual_covariance = H @ covariance_prediction @ H.T + self.observation_noise_covariance
        kalman_gain = covariance_prediction @ H.T @ np.linalg.inv(residual_covariance)
        self.state_ = state_prediction + kalman_gain @ residual_state
        self.covariance_ = (np.eye(self.covariance_.shape[0]) - kalman_gain @ H) @ covariance_prediction
        return

    def set_OD_variance_for_next_n_steps(self, new_variance, n):
        d = self.state_.shape[0]
        self._counter = n
        self._process_noise_covariance[np.arange(d - 1), np.arange(d - 1)] = new_variance

    def process_noise_covariance(self):
        if self._counter == 0:
            d = self.state_.shape[0]
            self._process_noise_covariance[
                np.arange(d - 1), np.arange(d - 1)
            ] = self._original_process_noise_variance
        self._counter -= 1
        return self._process_noise_covariance

    def _predict_state(self, state, covariance):
        return np.array([v * state[-1] for v in state[:-1]] + [state[-1]])

    def _predict_covariance(self, state, covariance):
        return (
            self._jacobian_process(state) @ covariance @ self._jacobian_process(state).T
            + self.process_noise_covariance()
        )

    def _jacobian_process(self, state):
        d = state.shape[0]
        J = np.zeros((d, d))

        rate = state[-1]
        ODs = state[:-1]

        J[np.arange(d - 1), np.arange(d - 1)] = rate
        J[np.arange(d - 1), np.arange(1, d)] = ODs
        J[-1, -1] = 1.0

        return J

    def _jacobian_observation(self):
        d = self.state_.shape[0]
        return np.eye(d)[: (d - 1)]
