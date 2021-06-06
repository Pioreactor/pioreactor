# -*- coding: utf-8 -*-
import signal, time, json, math
from collections import defaultdict
import click

from pioreactor.utils.streaming_calculations import ExtendedKalmanFilter
from pioreactor.utils import pio_jobs_running
from pioreactor.pubsub import subscribe, QOS

from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.actions.od_normalization import od_normalization

JOB_NAME = "growth_rate_calculating"


class GrowthRateCalculator(BackgroundJob):

    editable_settings = []

    def __init__(self, ignore_cache=False, unit=None, experiment=None):

        super(GrowthRateCalculator, self).__init__(
            job_name=JOB_NAME, unit=unit, experiment=experiment
        )

        self.ignore_cache = ignore_cache
        self.initial_growth_rate, self.od_normalization_factors, self.od_variances, self.od_blank = (
            self.get_precomputed_values()
        )
        self.initial_acc = 0
        self.time_of_previous_observation = time.time()
        self.expected_dt = 1 / (
            60 * 60 * config.getfloat("od_config.od_sampling", "samples_per_second")
        )
        self.ekf, self.channels_and_angles = self.initialize_extended_kalman_filter()
        self.start_passive_listeners()

    @property
    def state_(self):
        return self.ekf.state_

    def on_sleeping(self):
        # when the job sleeps, we expect a "big" jump in OD due to a few things:
        # 1. The delay between sleeping and resuming can causing a change in OD (as OD will keep changing)
        # 2. The user picks up the vial for inspection, places it back, but this causes an OD shift
        #    due to variation in the glass
        #
        # so to "fix" this, we will treat it like a dilution event, and modify the variances
        # TODO: this should occur _after_ sleeping ends....
        self.update_ekf_variance_after_event(minutes=0.5, factor=5e2)

    def initialize_extended_kalman_filter(self):
        import numpy as np

        latest_od_message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/od_raw_batched"
        )

        latest_ods = json.loads(latest_od_message.payload)["od_raw"]

        channels_and_initial_points = self.scale_raw_observations(
            self.batched_raw_od_readings_to_dict(latest_ods)
        )

        channels_and_angles = {
            channel: latest_ods[channel]["angle"]
            for channel in sorted(latest_ods, reverse=True)
        }

        initial_state = np.array(
            [
                *channels_and_initial_points.values(),
                self.initial_growth_rate,
                self.initial_acc,
            ]
        )

        d = initial_state.shape[0]

        # empirically selected - TODO: this should probably scale with `expected_dt`
        initial_covariance = 1e-8 * np.diag([1.0] * (d - 2) + [1.0, 5.0])
        self.logger.debug(f"Initial covariance matrix: {str(initial_covariance)}")

        acc_variance = config.getfloat("growth_rate_kalman", "acc_variance")
        acc_process_variance = (acc_variance * self.expected_dt) ** 2

        process_noise_covariance = np.zeros((d, d))
        process_noise_covariance[-1, -1] = acc_process_variance

        observation_noise_covariance = self.create_obs_noise_covariance(
            channels_and_initial_points
        )
        self.logger.debug(
            f"Observation noise covariance matrix: {str(observation_noise_covariance)}"
        )

        return (
            ExtendedKalmanFilter(
                initial_state,
                initial_covariance,
                process_noise_covariance,
                observation_noise_covariance,
            ),
            channels_and_angles,
        )

    def create_obs_noise_covariance(self, channels_and_initial_points):
        import numpy as np

        # our obs_variance is tuned well for std = state * 0.01,
        # so if we _actually_ observe something like std = state * 0.03, we should scale
        # that sensor's obs variance by 3
        #
        # eg: I observed 1.3e-07 in sensor A, with initial state  0.00958
        # sqrt(1.3e-07) / 0.00958 / 0.01 = 3.76362 is our scaling factor

        scaling_obs_variances = np.array(
            [
                math.sqrt(self.od_variances[channel])
                / channels_and_initial_points[channel]
                / 0.01
                for channel in channels_and_initial_points
            ]
        )

        obs_variances = config.getfloat(
            "growth_rate_kalman", "obs_variance"
        ) ** 2 * np.diag(scaling_obs_variances)
        return obs_variances

    def get_precomputed_values(self):
        if self.ignore_cache:
            assert (
                "od_reading" in pio_jobs_running()
            ), "OD reading should be running. Stopping."
            # the below will populate od_norm and od_variance too
            self.logger.info(
                "Computing OD normalization metrics. This may take a few minutes"
            )
            od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Completed OD normalization metrics.")
            initial_growth_rate = 0
        else:
            initial_growth_rate = self.get_growth_rate_from_broker()
        od_normalization_factors = self.get_od_normalization_from_broker()
        od_variances = self.get_od_variances_from_broker()
        od_blank = self.get_od_blank_from_broker()

        # what happens if od_blank is near / less than od_normalization_factors?
        # this means that the inoculant had near 0 impact on the turbidity => very dilute.
        # I think we should not use od_blank if so
        for angle in od_normalization_factors.keys():
            if od_normalization_factors[angle] * 0.95 < od_blank[angle]:
                self.logger.debug(
                    "Resetting od_blank because it is too close to current observations."
                )
                od_blank[angle] = od_normalization_factors[angle] * 0.95

        return initial_growth_rate, od_normalization_factors, od_variances, od_blank

    def get_od_blank_from_broker(self):
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_blank/mean",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return json.loads(message.payload)
        else:
            return defaultdict(lambda: 0)

    def get_growth_rate_from_broker(self):
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate_calculating/growth_rate",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return float(json.loads(message.payload)["growth_rate"])
        else:
            return 0

    def get_od_normalization_from_broker(self):
        # we check if the broker has variance/mean stats
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_normalization/mean",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return json.loads(message.payload)
        else:
            self.logger.debug("od_normalization/mean not found in broker.")
            self.logger.info(
                "Computing OD normalization metrics. This may take a few minutes"
            )
            od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Computing OD normalization metrics completed.")
            return self.get_od_normalization_from_broker()

    def get_od_variances_from_broker(self):
        # we check if the broker has variance/mean stats
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_normalization/variance",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return json.loads(message.payload)
        else:
            self.logger.debug("od_normalization/variance not found in broker.")
            self.logger.info(
                "Computing OD normalization metrics. This may take a few minutes"
            )
            od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Computing OD normalization metrics completed.")

            return self.get_od_variances_from_broker()

    def update_ekf_variance_after_event(self, minutes, factor):
        if is_testing_env():
            msg = subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval",
                timeout=1.0,
            )
            if msg:
                interval = float(msg.payload)
            else:
                interval = 1
            self.ekf.scale_OD_variance_for_next_n_seconds(
                factor, minutes * (12 * interval)
            )
        else:
            self.ekf.scale_OD_variance_for_next_n_seconds(factor, minutes * 60)

    def scale_raw_observations(self, observations):
        def scale_and_shift(obs, shift, scale):
            return (obs - shift) / (scale - shift)

        v = {
            channel: scale_and_shift(
                observations[channel],
                self.od_blank[channel],
                self.od_normalization_factors[channel],
            )
            for channel in self.od_normalization_factors.keys()
        }
        if any([v[a] < 0 for a in v]):
            self.logger.warning(f"Negative normalized value(s) observed: {v}")
            self.logger.debug(
                f"od_normalization_factors: {self.od_normalization_factors}"
            )
            self.logger.debug(f"od_blank: {self.od_blank}")

        return v

    def update_state_from_observation(self, message):
        if self.state != self.READY:
            return

        current_time = time.time()

        if is_testing_env():
            # when running a mock script, we run at an accelerated rate, but want to mimic
            # production.
            dt = self.expected_dt
        else:
            # TODO this should use the internal timestamp reference
            dt = (
                (current_time - self.time_of_previous_observation) / 60 / 60
            )  # delta time in hours

        payload = json.loads(message.payload)
        timestamp = payload["timestamp"]
        observations = self.batched_raw_od_readings_to_dict(payload["od_raw"])
        scaled_observations = self.scale_raw_observations(observations)

        try:
            self.ekf.update(list(scaled_observations.values()), dt)
        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(f"failed with {str(e)}")
            raise e
        else:
            # TODO: EKF values can be nans...
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/growth_rate",
                {"growth_rate": self.state_[-2], "timestamp": timestamp},
                retain=True,
            )

            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/kalman_filter_outputs",
                {
                    "state": self.ekf.state_.tolist(),
                    "covariance_matrix": self.ekf.covariance_.tolist(),
                    "timestamp": timestamp,
                },
            )

            for i, (channel, angle) in enumerate(self.channels_and_angles.items()):
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/od_filtered/{channel}",
                    {
                        "od_filtered": self.state_[i],
                        "timestamp": timestamp,
                        "angle": angle,
                    },
                )

            self.time_of_previous_observation = current_time
            return

    def response_to_dosing_event(self, message):
        # here we can add custom logic to handle dosing events.

        # an improvement to this: the variance factor is proportional to the amount exchanged.
        self.update_ekf_variance_after_event(minutes=1, factor=2500)

    def start_passive_listeners(self):
        # process incoming data
        self.subscribe_and_callback(
            self.update_state_from_observation,
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/od_raw_batched",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
        )
        self.subscribe_and_callback(
            self.response_to_dosing_event,
            f"pioreactor/{self.unit}/{self.experiment}/dosing_events",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
        )

        # if the stirring is changed, this can effect the OD level, but not the
        # growth rate. Let's treat it the same how we treat a dosing event.
        # self.subscribe_and_callback(
        #     lambda m: self.update_ekf_variance_after_event(0.3, 5e2),
        #     f"pioreactor/{self.unit}/{self.experiment}/stirring/duty_cycle",
        #     qos=QOS.EXACTLY_ONCE,
        #     allow_retained=False,
        # )
        # removed for now, because it was messing with the new dynamic stirring

    @staticmethod
    def batched_raw_od_readings_to_dict(raw_od_readings):
        """
        Inputs looks like
        {
            "0": {"voltage": 0.13, "angle": "135,45"},
            "1": {"voltage": 0.03, "angle": "90,135"}
        }

        """
        return {
            channel: float(raw_od_readings[channel]["voltage"])
            for channel in sorted(raw_od_readings, reverse=True)
        }


@click.command(name="growth_rate_calculating")
@click.option("--ignore-cache", is_flag=True, help="Ignore the cached growth_rate value")
def click_growth_rate_calculating(ignore_cache):
    """
    Start calculating growth rate
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    calculator = GrowthRateCalculator(  # noqa: F841
        ignore_cache=ignore_cache, unit=unit, experiment=experiment
    )
    signal.pause()
