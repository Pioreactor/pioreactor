# -*- coding: utf-8 -*-
import time
import json
import os
import signal
from collections import defaultdict
from statistics import median

import numpy as np
import click

from morbidostat.utils.streaming_calculations import ExtendedKalmanFilter
from morbidostat.pubsub import publish, subscribe, subscribe_and_callback

from morbidostat.whoami import unit, experiment
from morbidostat.config import config, leader_hostname
from morbidostat.background_jobs import BackgroundJob

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class GrowthRateCalculator(BackgroundJob):

    editable_settings = []

    def __init__(self, ignore_cache=False, unit=None, experiment=None, verbose=0):
        super(GrowthRateCalculator, self).__init__(job_name=JOB_NAME, verbose=verbose, unit=unit, experiment=experiment)
        self.ignore_cache = ignore_cache
        self.initial_growth_rate = 0.0
        self.ekf = None
        self.od_normalization_factors = defaultdict(lambda: 1)
        self.od_variances = defaultdict(lambda: 1e-5)
        self.samples_per_minute = 60 * float(config["od_sampling"]["samples_per_second"])
        self.start_passive_listeners()

        time.sleep(3.0)
        self.ekf, self.angles = self.initialize_extended_kalman_filter()

    @property
    def state_(self):
        return self.ekf.state_

    def initialize_extended_kalman_filter(self):
        message = subscribe(f"morbidostat/{self.unit}/{self.experiment}/od_raw_batched")
        angles_and_initial_points = self.scale_raw_observations(self.json_to_sorted_dict(message.payload))

        # growth rate in MQTT is hourly, convert back to multiplicative
        initial_rate = self.exp_rate_to_multiplicative_rate(self.initial_growth_rate)
        initial_state = np.array([*angles_and_initial_points.values(), initial_rate])

        d = initial_state.shape[0]

        # empirically selected
        initial_covariance = np.block(
            [[1e-5 * np.ones((d - 1, d - 1)), 1e-8 * np.ones((d - 1, 1))], [1e-8 * np.ones((1, d - 1)), 1e-8]]
        )
        OD_process_covariance = self.create_OD_covariance(angles_and_initial_points.keys())

        rate_process_variance = 5e-14
        process_noise_covariance = np.block(
            [[OD_process_covariance, 0 * np.ones((d - 1, 1))], [0 * np.ones((1, d - 1)), rate_process_variance]]
        )
        observation_noise_covariance = self.create_obs_noise_covariance(angles_and_initial_points.keys())

        return (
            ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance),
            angles_and_initial_points.keys(),
        )

    def create_obs_noise_covariance(self, angles):
        # add a fudge factor
        # I've seen a ~30-fold increase in the variance over time.
        return 30 * np.diag([self.od_variances[angle] / self.od_normalization_factors[angle] ** 2 for angle in angles])

    def set_initial_growth_rate(self, message):
        self.initial_growth_rate = float(message.payload)

    def set_od_normalization_factors(self, message):
        self.od_normalization_factors = self.json_to_sorted_dict(message.payload)

    def set_od_variances(self, message):
        self.od_variances = self.json_to_sorted_dict(message.payload)

    def multiplicative_rate_to_exp_rate(self, mrate):
        return np.log(mrate) * 60 * self.samples_per_minute

    def exp_rate_to_multiplicative_rate(self, erate):
        return np.exp(erate / 60 / self.samples_per_minute)

    def update_ekf_variance_after_io_event(self, message):
        self.ekf.scale_OD_variance_for_next_n_steps(2e4, 2 * self.samples_per_minute)

    def scale_raw_observations(self, observations):
        return {angle: observations[angle] / self.od_normalization_factors[angle] for angle in observations.keys()}

    def update_state_from_observation(self, message):
        if self.state != self.READY:
            return

        if self.ekf is None:
            # pass to wait for state to initialize
            return

        try:
            observations = self.json_to_sorted_dict(message.payload)
            scaled_observations = self.scale_raw_observations(observations)
            self.ekf.update(list(scaled_observations.values()))

            publish(
                f"morbidostat/{self.unit}/{self.experiment}/growth_rate",
                self.multiplicative_rate_to_exp_rate(self.state_[-1]),
                verbose=self.verbose,
                retain=True,
            )

            for i, angle_label in enumerate(self.angles):
                publish(
                    f"morbidostat/{self.unit}/{self.experiment}/od_filtered/{angle_label}", self.state_[i], verbose=self.verbose
                )

            return

        except Exception as e:
            publish(
                f"morbidostat/{self.unit}/{self.experiment}/error_log",
                f"[{JOB_NAME}]: failed {e}. Skipping.",
                verbose=self.verbose,
            )

    def start_passive_listeners(self):
        # initialize states
        if not self.ignore_cache:
            self.pubsub_clients.append(
                subscribe_and_callback(
                    self.set_initial_growth_rate, f"morbidostat/{self.unit}/{self.experiment}/growth_rate", timeout=3, max_msgs=1
                )
            )

        self.pubsub_clients.append(
            subscribe_and_callback(
                self.set_od_normalization_factors,
                f"morbidostat/{self.unit}/{self.experiment}/od_normalization/median",
                timeout=3,
                max_msgs=1,
            )
        )

        self.pubsub_clients.append(
            subscribe_and_callback(
                self.set_od_variances,
                f"morbidostat/{self.unit}/{self.experiment}/od_normalization/variance",
                timeout=3,
                max_msgs=1,
            )
        )

        # process incoming data
        self.pubsub_clients.append(
            subscribe_and_callback(
                self.update_state_from_observation, f"morbidostat/{self.unit}/{self.experiment}/od_raw_batched"
            )
        )
        self.pubsub_clients.append(
            subscribe_and_callback(
                self.update_ekf_variance_after_io_event, f"morbidostat/{self.unit}/{self.experiment}/io_events"
            )
        )

    @staticmethod
    def json_to_sorted_dict(json_dict):
        d = json.loads(json_dict)
        return {k: float(d[k]) for k in sorted(d, reverse=True) if not k.startswith("180")}

    @staticmethod
    def create_OD_covariance(angles):
        # increasing Q increases the uncertainty of our prediction
        d = len(angles)
        variances = {"135": 1e-7, "90": 1e-7, "45": 1e-7}

        OD_covariance = 0 * np.ones((d, d))
        for i, a in enumerate(angles):
            for k in variances:
                if a.startswith(k):
                    OD_covariance[i, i] = variances[k]
        return OD_covariance


def growth_rate_calculating(verbose, ignore_cache):
    calculator = GrowthRateCalculator(verbose=verbose, ignore_cache=ignore_cache, unit=unit, experiment=experiment)
    while True:
        signal.pause()


@click.command()
@click.option("--verbose", "-v", count=True, help="Print to std out")
@click.option("--ignore-cache", is_flag=True, help="Ignore the cached growth_rate value")
def click_growth_rate_calculating(verbose, ignore_cache):
    growth_rate_calculating(verbose, ignore_cache)


if __name__ == "__main__":
    click_growth_rate_calculating()
