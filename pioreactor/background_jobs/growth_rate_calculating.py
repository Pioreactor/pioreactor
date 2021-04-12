# -*- coding: utf-8 -*-
import signal, time, json

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
        self.initial_growth_rate, self.od_normalization_factors, self.od_variances = (
            self.set_precomputed_values()
        )
        self.initial_acc = 0
        self.time_of_previous_observation = time.time()
        self.expected_dt = 1 / (
            60 * 60 * config.getfloat("od_config.od_sampling", "samples_per_second")
        )
        self.ekf, self.angles = self.initialize_extended_kalman_filter()
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
        self.update_ekf_variance_after_event(minutes=0.5, factor=5e2)

    def initialize_extended_kalman_filter(self):
        import numpy as np

        latest_od = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched",
            allow_retained=False,
        )
        angles_and_initial_points = self.scale_raw_observations(
            self.json_to_sorted_dict(latest_od.payload)
        )

        initial_state = np.array(
            [
                *angles_and_initial_points.values(),
                self.initial_growth_rate,
                self.initial_acc,
            ]
        )

        d = initial_state.shape[0]

        # empirically selected
        initial_covariance = 1e-6 * np.diag([1.0] * (d - 2) + [0.5, 0.5])

        acc_variance = config.getfloat("growth_rate_kalman", "acc_variance")
        acc_process_variance = (acc_variance * self.expected_dt) ** 2

        process_noise_covariance = np.zeros((d, d))
        process_noise_covariance[-1, -1] = acc_process_variance

        observation_noise_covariance = self.create_obs_noise_covariance(
            angles_and_initial_points.keys()
        )
        return (
            ExtendedKalmanFilter(
                initial_state,
                initial_covariance,
                process_noise_covariance,
                observation_noise_covariance,
            ),
            angles_and_initial_points.keys(),
        )

    def create_obs_noise_covariance(self, angles):
        import numpy as np

        # if a sensor has X times the variance of the other, we should encode this in the obs. covariance.
        obs_variances = np.array([self.od_variances[angle] for angle in angles])
        obs_variances = obs_variances / obs_variances.min()

        return config.getfloat("growth_rate_kalman", "obs_variance") ** 2 * np.diag(
            obs_variances
        )

    def set_precomputed_values(self):
        if self.ignore_cache:
            assert (
                "od_reading" in pio_jobs_running()
            ), "OD reading should be running. Stopping."
            # the below will populate od_norm and od_variance too
            self.logger.info(
                "Computing OD normalization metrics. This may take a few minutes"
            )
            od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Computing OD normalization metrics completed.")
            initial_growth_rate = 0
        else:
            initial_growth_rate = self.get_growth_rate_from_broker()

        od_normalization_factors = self.get_od_normalization_from_broker()
        od_variances = self.get_od_variances_from_broker()
        return initial_growth_rate, od_normalization_factors, od_variances

    def get_growth_rate_from_broker(self):
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return float(message.payload)
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
            return self.json_to_sorted_dict(message.payload)
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
            return self.json_to_sorted_dict(message.payload)
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
            interval = float(
                subscribe(
                    f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval"
                ).payload
            )
            self.ekf.scale_OD_variance_for_next_n_seconds(
                factor, minutes * (12 * interval)
            )
        else:
            self.ekf.scale_OD_variance_for_next_n_seconds(factor, minutes * 60)

    def scale_raw_observations(self, observations):
        return {
            angle: observations[angle] / self.od_normalization_factors[angle]
            for angle in self.od_normalization_factors.keys()
        }

    def update_state_from_observation(self, message):
        if self.state != self.READY:
            return

        current_time = time.time()

        if is_testing_env():
            # when running a mock script, we run at an accelerated rate, but want to mimic
            # production.
            dt = self.expected_dt
        else:
            dt = (
                (current_time - self.time_of_previous_observation) / 60 / 60
            )  # delta time in hours

        observations = self.json_to_sorted_dict(message.payload)
        scaled_observations = self.scale_raw_observations(observations)
        try:
            self.ekf.update(list(scaled_observations.values()), dt)
        except Exception as e:
            self.logger.error(f"failed with {str(e)}")
            raise e
        else:
            # TODO: EKF values can be nans...
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/growth_rate",
                self.state_[-2],
                retain=True,
            )

            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/kalman_filter_outputs",
                json.dumps(
                    {
                        "state": self.ekf.state_.tolist(),
                        "covariance_matrix": self.ekf.covariance_.tolist(),
                    }
                ),
            )

            for i, angle_label in enumerate(self.angles):
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/od_filtered/{angle_label}",
                    self.state_[i],
                )

            self.time_of_previous_observation = current_time
            return

    def response_to_dosing_event(self, message):
        # here we can add custom logic to handle dosing events.
        # for example, in continuous_cycle automation, we dont want to respond to
        # dosing events (because they are so small and so frequent)

        payload = json.loads(message.payload)
        if payload["source_of_event"] == "dosing_automation:ContinuousCycle":
            return

        # an improvement to this: the variance factor is proportional to the amount exchanged.
        self.update_ekf_variance_after_event(minutes=1, factor=2500)

    def start_passive_listeners(self):
        # process incoming data
        self.subscribe_and_callback(
            self.update_state_from_observation,
            f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched",
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
    def json_to_sorted_dict(json_dict):
        d = json.loads(json_dict)
        return {
            k: float(d[k]) for k in sorted(d, reverse=True) if not k.startswith("180")
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
    while True:
        signal.pause()
