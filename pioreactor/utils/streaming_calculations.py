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


class CultureGrowthEKF:
    """
    Modified from the algorithm in
    https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0181923#pone.0181923.s007

    The idea is that each sensor will evolve like, using notation from the wikipedia page

    ```
    m_{1,t}, m_{2,t} are our sensor measurements (could be more, example here is for two sensors)

    m_{1,t} = g1(OD_{t-1}) + noise   # noise here includes temperature changes, EM noise,
    m_{2,t} = g2(OD_{t-1}) + noise
    OD_t = OD_{t-1} * exp(r_{t-1} * Δt) + noise
    r_t = r_{t-1} + a_{t-1} * Δt + noise
    a_t = a_{t-1} + noise

    # g1 and g2 are generic functions. Often they are the identity function, but if using a 180deg sensor
    # then it would be the inverse function.
    # they could also be functions that model saturation...


    Let X = [OD, r, a]

    f([OD, r, a]) = [OD * exp(r Δt), r + a Δt, a]
    h([OD, r, a]) = [OD, OD]  # recall this is a function of the number of sensors

    jac(f) = [
        [exp(r Δt),  OD * exp(r Δt) * Δt,  0],
        [0,          1,                    Δt],
        [0,          0,                    1],
    ]

    jac(h) = [
        [1, 0, 0],
        [1, 0, 0]
    ]

    ```

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
        import numpy as np

        initial_state = np.asarray(initial_state)

        assert initial_state.shape[0] == 3
        assert (
            initial_state.shape[0]
            == initial_covariance.shape[0]
            == initial_covariance.shape[1]
        ), f"Shapes are not correct,{initial_state.shape[0]}, {initial_covariance.shape[0]}, {initial_covariance.shape[1]}"
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

        self._currently_scaling_covariance = False
        self._currently_scaling_process_covariance = False
        self._scale_covariance_timer = None
        self._covariance_pre_scale = None

    def predict(self, dt):
        return (
            self._predict_state(self.state_, self.covariance_, dt),
            self._predict_covariance(self.state_, self.covariance_, dt),
        )

    def update(self, observation, dt):
        import numpy as np

        observation = np.asarray(observation)
        assert observation.shape[0] == self.n_sensors, (observation, self.n_sensors)

        state_prediction, covariance_prediction = self.predict(dt)
        residual_state = observation - state_prediction[:-2]
        H = self._jacobian_observation()
        residual_covariance = (
            # see Scaling note above for why we multiple by state_[0]
            H @ covariance_prediction @ H.T
            + self.state_[0] * self.observation_noise_covariance
        )

        kalman_gain_ = np.linalg.solve(
            residual_covariance.T, (H @ covariance_prediction.T)
        ).T
        self.state_ = state_prediction + kalman_gain_ @ residual_state
        self.covariance_ = (
            np.eye(self.n_states) - kalman_gain_ @ H
        ) @ covariance_prediction
        return

    def scale_OD_variance_for_next_n_seconds(self, factor, seconds):
        """
        This is a bit tricky: we do some state handling here (eg: keeping track of the previous covariance matrix)
        but we will be invoking this function multiple times. So we start a Timer but cancel it
        if we invoke this function again (i.e. a new dosing event). The if the Timer successfully
        executes its function, then we restore state (add back the covariance matrix.)

        TODO: this should be decoupled from the EKF class.

        """
        import numpy as np

        def reverse_scale_covariance():
            self._currently_scaling_covariance = False
            self.covariance_ = self._covariance_pre_scale
            self._covariance_pre_scale = None

        def forward_scale_covariance():
            if not self._currently_scaling_covariance:
                self._covariance_pre_scale = self.covariance_.copy()

            self._currently_scaling_covariance = True
            self.covariance_ = np.diag(self._covariance_pre_scale.diagonal())
            self.covariance_[0] *= factor

        def forward_scale_process_covariance():
            if not self._currently_scaling_process_covariance:
                self._dummy = self.process_noise_covariance[2, 2]

            self._currently_scaling_process_covariance = True
            self.process_noise_covariance[0, 0] = 1e-7 * self.state_[0]
            self.process_noise_covariance[2, 2] = 0

        def reverse_scale_process_covariance():
            self._currently_scaling_process_covariance = False
            self.process_noise_covariance[0, 0] = 0
            self.process_noise_covariance[2, 2] = self._dummy

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
        state = [OD, r, a]

        OD_t = OD_{t-1} * exp(r_{t-1} * Δt)
        r_t = r_{t-1} + a_{t-1}Δt
        a_t = a_{t-1}

        """
        import numpy as np

        od, rate, acc = state
        return np.array([od * np.exp(rate * dt), rate + acc * dt, acc])

    def _predict_covariance(self, state, covariance, dt):
        jacobian = self._jacobian_process(state, dt)
        return jacobian @ covariance @ jacobian.T + self.process_noise_covariance

    def _jacobian_process(self, state, dt):
        """
        The prediction process is

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

    def _jacobian_observation(self):
        """
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
        import numpy as np

        n = self.n_sensors
        J = np.zeros((n, 3))
        J[:, 0] = 1
        return J

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
