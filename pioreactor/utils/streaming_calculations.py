# -*- coding: utf-8 -*-
from json import dumps
from threading import Timer
from pioreactor.pubsub import publish


class ExponentialMovingAverage:
    def __init__(self, alpha):
        self.value = None
        self.alpha = alpha

    def update(self, new_value):
        if self.value is None:
            self.value = new_value
        else:
            self.value = (1 - self.alpha) * new_value + self.alpha * self.value
        return self.value


class ExtendedKalmanFilter:
    """
    Modified from the algorithm in
    https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0181923#pone.0181923.s007

    The idea is that each sensor will evolve like:

    OD_{i, t+1} = OD_{i, t} * r_t
    r_{t+1} = r_t

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

    Uncertainty
    ------------
    Because of the model, the lower bound on the rate estimate's variance is Q[-1, -1].

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
    ):
        assert (
            initial_state.shape[0]
            == initial_covariance.shape[0]
            == initial_covariance.shape[1]
        ), f"Shapes are not correct,{initial_state.shape[0]}, {initial_covariance.shape[0]}, {initial_covariance.shape[1]}"
        assert process_noise_covariance.shape == initial_covariance.shape
        assert observation_noise_covariance.shape[0] == (initial_covariance.shape[0] - 2)
        assert self._is_positive_definite(process_noise_covariance)
        assert self._is_positive_definite(initial_covariance)
        assert self._is_positive_definite(observation_noise_covariance)
        import numpy as np

        self.process_noise_covariance = process_noise_covariance
        self.observation_noise_covariance = observation_noise_covariance
        self.state_ = initial_state
        self.covariance_ = initial_covariance
        self.dim = self.state_.shape[0]

        self._currently_scaling_covariance = False
        self._currently_scaling_process_covariance = False
        self._scale_covariance_timer = None
        self._covariance_pre_scale = None

        self._original_process_noise_variance = np.diag(self.process_noise_covariance)[
            : (self.dim - 2)
        ].copy()

    def predict(self, dt):
        return (
            self._predict_state(self.state_, self.covariance_, dt),
            self._predict_covariance(self.state_, self.covariance_, dt),
        )

    def update(self, observation, dt):
        import numpy as np

        observation = np.asarray(observation)
        assert (observation.shape[0] + 2) == self.state_.shape[0], (
            (observation.shape[0] + 2),
            self.state_.shape[0],
        )
        state_prediction, covariance_prediction = self.predict(dt)
        residual_state = observation - state_prediction[:-2]
        H = self._jacobian_observation()
        residual_covariance = (
            # see Scaling note above for why we multiple by state_
            H @ covariance_prediction @ H.T
            + self.state_[:-2] ** 2 * self.observation_noise_covariance
        )

        kalman_gain_ = np.linalg.solve(
            residual_covariance.T, (H @ covariance_prediction.T)
        ).T
        self.state_ = state_prediction + kalman_gain_ @ residual_state
        self.covariance_ = (np.eye(self.dim) - kalman_gain_ @ H) @ covariance_prediction
        return

    def scale_OD_variance_for_next_n_seconds(self, factor, seconds):
        """
        This is a bit tricky: we do some state handling here (eg: keeping track of the previous covariance matrix)
        but we will be invoking this function multiple times. So we start a Timer but cancel it
        if we invoke this function again (i.e. a new dosing event). The if the Timer successfully
        executes its function, then we restore state (add back the covariance matrix.)

        """
        import numpy as np

        d = self.dim

        def reverse_scale_covariance():
            self._currently_scaling_covariance = False
            # we take the geometric mean
            self.covariance_ = self._covariance_pre_scale
            self._covariance_pre_scale = None

        def forward_scale_covariance():
            if not self._currently_scaling_covariance:
                self._covariance_pre_scale = self.covariance_.copy()

            self._currently_scaling_covariance = True
            self.covariance_ = np.diag(self._covariance_pre_scale.diagonal())
            self.covariance_[np.arange(d - 2), np.arange(d - 2)] *= factor

        def forward_scale_process_covariance():
            if not self._currently_scaling_process_covariance:
                self._dummy = self.process_noise_covariance[-1, -1]

            self._currently_scaling_process_covariance = True
            self.process_noise_covariance[np.arange(d - 2), np.arange(d - 2)] = (
                1e-7 * self.state_[:-2]
            )
            self.process_noise_covariance[-1, -1] = 0

        def reverse_scale_process_covariance():
            self._currently_scaling_process_covariance = False
            self.process_noise_covariance[np.arange(d - 2), np.arange(d - 2)] = 0
            self.process_noise_covariance[-1, -1] = self._dummy

        if self._currently_scaling_covariance:
            self._scale_covariance_timer.cancel()

        if self._currently_scaling_process_covariance:
            self._scale_process_covariance_timer.cancel()

        self._scale_covariance_timer = Timer(seconds, reverse_scale_covariance)
        self._scale_covariance_timer.daemon = True
        self._scale_covariance_timer.start()

        self._scale_process_covariance_timer = Timer(
            2.5 * seconds, reverse_scale_process_covariance
        )
        self._scale_process_covariance_timer.daemon = True
        self._scale_process_covariance_timer.start()

        forward_scale_covariance()
        forward_scale_process_covariance()

    def _predict_state(self, state, covariance, dt):
        """
        The prediction process is

            OD_{1, t+1} = OD_{1, t} * exp(r_t ∆t)
            OD_{2, t+1} = OD_{2, t} * exp(r_t ∆t)
            ...
            r_{t+1} = r_t + a_t ∆t
            a_{t+1} = a_t

        """
        import numpy as np

        ODs = state[:-2]
        rate = state[-2]
        acc = state[-1]
        return np.array([od * np.exp(rate * dt) for od in ODs] + [rate + acc * dt, acc])

    def _predict_covariance(self, state, covariance, dt):
        jacobian = self._jacobian_process(state, dt)
        return jacobian @ covariance @ jacobian.T + self.process_noise_covariance

    def _jacobian_process(self, state, dt):
        import numpy as np

        """
        The prediction process is

            OD_{1, t+1} = OD_{1, t} * exp(r_t ∆t)
            OD_{2, t+1} = OD_{2, t} * exp(r_t ∆t)
            ...
            r_{t+1} = r_t + a_t ∆t
            a_{t+1} = a_t

        So jacobian should look like:

             d(OD_1 * exp(r ∆t))/dOD_1   d(OD_1 * exp(r ∆t))/dOD_2 ... d(OD_1 * exp(r ∆t))/dr   d(OD_1 * exp(r ∆t))/da
             d(OD_2 * exp(r ∆t))/dOD_1   d(OD_2 * exp(r ∆t))/dOD_2 ... d(OD_2 * exp(r ∆t))/dr   d(OD_2 * exp(r ∆t))/da
             ...
             d(r)/dOD_1                  d(r)/dOD_2 ...                d(r)/dr                  d(r)/da
             d(a)/dOD_1                  d(a)/dOD_2                    d(a)/dr                  d(a)/da


        Which equals

            exp(r ∆t)   0            ...  OD_1 ∆t exp(r ∆t)     0
            0           exp(r ∆t)    ...  OD_2 ∆t exp(r ∆t)     0
            ...
            0            0                1                     ∆t
            0            0                0                     1

        """
        d = self.dim
        J = np.zeros((d, d))

        rate = state[-2]
        ODs = state[:-2]
        J[np.arange(d - 2), np.arange(d - 2)] = np.exp(rate * dt)
        J[np.arange(d - 2), -2] = ODs * np.exp(rate * dt) * dt

        J[-2, -2] = 1.0
        J[-2, -1] = dt
        J[-1, -1] = 1.0

        return J

    def _jacobian_observation(self):
        import numpy as np

        """
        We only observe the ODs
        """
        d = self.dim
        return np.eye(d)[: (d - 2)]

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
    """
    TODO

    """

    def __init__(
        self,
        Kp,
        Ki,
        Kd,
        K0=0,
        setpoint=None,
        output_limits=(None, None),
        sample_time=None,
        unit=None,
        experiment=None,
        job_name=None,
        target_name=None,
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
        self.target_name = target_name
        self.job_name = job_name

    def set_setpoint(self, new_setpoint):
        self.pid.setpoint = new_setpoint

    def update(self, input_, dt):
        output = self.pid(input_, dt) + self.K0
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
            "K0": self.K0,
            "integral": self.pid._integral,
            "proportional": self.pid._proportional,
            "derivative": self.pid._derivative,
            "latest_input": self.pid._last_input,
            "latest_output": self.pid._last_output,
            "job_name": self.job_name,
            "target_name": self.target_name,
        }
        publish(f"pioreactor/{self.unit}/{self.experiment}/pid_log", dumps(to_send))
