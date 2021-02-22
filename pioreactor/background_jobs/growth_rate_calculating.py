# -*- coding: utf-8 -*-
import json
import os
import signal
import logging

import click

from pioreactor.utils.streaming_calculations import ExtendedKalmanFilter
from pioreactor.utils import pio_jobs_running
from pioreactor.pubsub import subscribe, QOS

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.actions.od_normalization import od_normalization

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


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
        self.samples_per_minute = 60 * config.getfloat(
            "od_config.od_sampling", "samples_per_second"
        )
        self.dt = (
            1 / config.getfloat("od_config.od_sampling", "samples_per_second") / 60 / 60
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
        self.update_ekf_variance_after_event()

    def initialize_extended_kalman_filter(self):
        import numpy as np

        latest_od = subscribe(f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched")
        angles_and_initial_points = self.scale_raw_observations(
            self.json_to_sorted_dict(latest_od.payload)
        )

        initial_state = np.array(
            [*angles_and_initial_points.values(), self.initial_growth_rate]
        )

        d = initial_state.shape[0]

        # empirically selected
        initial_covariance = 0.0001 * np.diag(initial_state.tolist()[:-1] + [0.00001])

        OD_process_covariance = self.create_OD_covariance(
            angles_and_initial_points.keys()
        )

        rate_process_variance = (
            config.getfloat("growth_rate_kalman", "rate_variance") * self.dt
        ) ** 2
        process_noise_covariance = np.block(
            [
                [OD_process_covariance, 0 * np.ones((d - 1, 1))],
                [0 * np.ones((1, d - 1)), rate_process_variance],
            ]
        )
        observation_noise_covariance = self.create_obs_noise_covariance(
            angles_and_initial_points.keys()
        )
        return (
            ExtendedKalmanFilter(
                initial_state,
                initial_covariance,
                process_noise_covariance,
                observation_noise_covariance,
                dt=self.dt,
            ),
            angles_and_initial_points.keys(),
        )

    def create_obs_noise_covariance(self, angles):
        import numpy as np

        # if a sensor has X times the variance of the other, we should encode this in the obs. covariance.
        obs_variances = np.array([self.od_variances[angle] for angle in angles])
        obs_variances = obs_variances / obs_variances.min()

        # add a fudge factor
        fudge = 100
        return fudge * (0.05 * self.dt) ** 2 * np.diag(obs_variances)

    def create_OD_covariance(self, angles):
        import numpy as np

        d = len(angles)
        variances = {
            "135": (config.getfloat("growth_rate_kalman", "od_variance") * self.dt) ** 2,
            "90": (config.getfloat("growth_rate_kalman", "od_variance") * self.dt) ** 2,
            "45": (config.getfloat("growth_rate_kalman", "od_variance") * self.dt) ** 2,
        }

        OD_covariance = 0 * np.ones((d, d))
        for i, a in enumerate(angles):
            for k in variances:
                if a.startswith(k):
                    OD_covariance[i, i] = variances[k]
        return OD_covariance

    def set_precomputed_values(self):
        if self.ignore_cache:
            assert (
                "od_reading" in pio_jobs_running()
            ), "OD reading should be running. Stopping."
            # the below will populate od_norm and od_variance too
            od_normalization(unit=self.unit, experiment=self.experiment)
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
        # we check if the broker has variance/median stats
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_normalization/median",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return self.json_to_sorted_dict(message.payload)
        else:
            self.logger.debug("od_normalization/median not found in broker.")
            od_normalization(unit=self.unit, experiment=self.experiment)
            return self.get_od_normalization_from_broker()

    def get_od_variances_from_broker(self):
        # we check if the broker has variance/median stats
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_normalization/variance",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return self.json_to_sorted_dict(message.payload)
        else:
            self.logger.debug("od_normalization/variance not found in broker.")
            od_normalization(unit=self.unit, experiment=self.experiment)
            return self.get_od_variances_from_broker()

    def update_ekf_variance_after_event(self):
        self.ekf.scale_OD_variance_for_next_n_steps(
            5e3, round(0.5 * self.samples_per_minute)
        )

    def scale_raw_observations(self, observations):
        return {
            angle: observations[angle] / self.od_normalization_factors[angle]
            for angle in observations.keys()
        }

    def update_state_from_observation(self, message):
        if self.state != self.READY:
            return
        try:
            observations = self.json_to_sorted_dict(message.payload)
            scaled_observations = self.scale_raw_observations(observations)
            self.ekf.update(list(scaled_observations.values()))

            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/growth_rate",
                self.state_[-1],
                retain=True,
            )

            for i, angle_label in enumerate(self.angles):
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/od_filtered/{angle_label}",
                    self.state_[i],
                )

            return

        except Exception as e:
            self.logger.error(f"failed with {str(e)}")
            raise e

    def start_passive_listeners(self):
        # process incoming data
        self.subscribe_and_callback(
            self.update_state_from_observation,
            f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched",
            qos=QOS.EXACTLY_ONCE,
        )
        self.subscribe_and_callback(
            lambda m: self.update_ekf_variance_after_event(),
            f"pioreactor/{self.unit}/{self.experiment}/dosing_events",
            qos=QOS.EXACTLY_ONCE,
        )

    @staticmethod
    def json_to_sorted_dict(json_dict):
        d = json.loads(json_dict)
        return {
            k: float(d[k]) for k in sorted(d, reverse=True) if not k.startswith("180")
        }


def growth_rate_calculating(ignore_cache):
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:
        calculator = GrowthRateCalculator(  # noqa: F841
            ignore_cache=ignore_cache, unit=unit, experiment=experiment
        )
        while True:
            signal.pause()
    except Exception as e:
        logging.getLogger(JOB_NAME).error(f"{str(e)}")
        raise e


@click.command(name="growth_rate_calculating")
@click.option("--ignore-cache", is_flag=True, help="Ignore the cached growth_rate value")
def click_growth_rate_calculating(ignore_cache):
    """
    Start calculating growth rate
    """
    growth_rate_calculating(ignore_cache)
