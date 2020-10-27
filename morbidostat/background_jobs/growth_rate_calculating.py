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
from morbidostat.utils import log_start, log_stop
from morbidostat.whoami import unit, experiment
from morbidostat.config import config, leader_hostname
from morbidostat.background_jobs import BackgroundJob

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class MedianFirstN:
    def __init__(self, N=20):
        self.N = N
        self.counter = defaultdict(lambda: 0)
        self.raw_data = defaultdict(list)
        self.reduced_data = {}

    def update(self, data):
        for key, v in data.items():
            if self.counter[key] < self.N:
                self.counter[key] += 1
                self.raw_data[key].append(v)

                if self.counter[key] == self.N:
                    self.reduced_data[key] = median(self.raw_data[key])
                    # publish
                    publish(
                        f"morbidostat/{unit}/{experiment}/od_normalization_factors", json.dumps(self.reduced_data), retain=True
                    )

    def __getitem__(self, key):
        if self.counter[key] < self.N:
            return None
        else:
            return self.reduced_data[key]

    @classmethod
    def from_dict(cls, dict_):
        m = MedianFirstN()
        m.reduced_data = dict_
        m.counter = defaultdict(lambda: 0, [(k, m.N) for k in dict_])
        return m


class GrowthRateCalculator(BackgroundJob):

    publish_out = []

    def __init__(self, unit=None, experiment=None, verbose=0):
        super(GrowthRateCalculator, self).__init__(job_name=JOB_NAME, verbose=verbose, unit=unit, experiment=experiment)
        self.initial_growth_rate = 0.0
        self.od_normalization_factors = MedianFirstN(N=20)
        self.ekf = None
        self.samples_per_minute = 60 * float(config["od_sampling"]["samples_per_second"])
        self.start_passive_listeners()

        time.sleep(1.0)
        self.ekf, self.angles = self.initialize_extended_kalman_filter()

    def initialize_extended_kalman_filter(self):
        message = subscribe(f"morbidostat/{self.unit}/{self.experiment}/od_raw_batched")
        angles_and_initial_points = self.json_to_sorted_dict(message.payload)

        # growth rate in MQTT is hourly, convert back to multiplicative
        initial_rate = self.exp_rate_to_multiplicative_rate(self.initial_growth_rate)
        initial_state = np.array([*angles_and_initial_points.values(), initial_rate])

        d = initial_state.shape[0]

        # empirically selected
        initial_covariance = np.block(
            [[1e-5 * np.ones((d - 1, d - 1)), 1e-8 * np.ones((d - 1, 1))], [1e-8 * np.ones((1, d - 1)), 1e-8]]
        )
        OD_process_covariance = self.create_OD_covariance(angles_and_initial_points.keys())

        # think of rate_process_variance as a weighting between how much do I trust the model (lower value => rate_t = rate_{t-1}) vs how much do I trust the observations
        rate_process_variance = 1e-10
        process_noise_covariance = np.block(
            [[OD_process_covariance, 1e-12 * np.ones((d - 1, 1))], [1e-12 * np.ones((1, d - 1)), rate_process_variance]]
        )
        observation_noise_covariance = 1e-3 * np.eye(d - 1)

        return (
            ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance),
            angles_and_initial_points.keys(),
        )

    def set_initial_growth_rate(self, message):
        self.initial_growth_rate = float(message.payload)

    def set_od_normalization_factors(self, message):
        seed = json.loads(message.payload)
        self.od_normalization_factors = MedianFirstN.from_dict(seed)

    @property
    def state_(self):
        return self.ekf.state_

    def multiplicative_rate_to_exp_rate(self, mrate):
        return np.log(mrate) * 60 * self.samples_per_minute

    def exp_rate_to_multiplicative_rate(self, erate):
        return np.exp(erate / 60 / self.samples_per_minute)

    def update_ekf_variance_after_io_event(self, message):
        self.ekf.scale_OD_variance_for_next_n_steps(5e3, 2 * self.samples_per_minute)

    def update_state_from_observation(self, message):
        if not self.active:
            return

        if self.ekf is None:
            # pass to wait for state to initialize
            return

        try:
            observations = self.json_to_sorted_dict(message.payload)
            self.ekf.update(list(observations.values()))
            self.od_normalization_factors.update(observations)

            publish(
                f"morbidostat/{self.unit}/{self.experiment}/growth_rate",
                self.multiplicative_rate_to_exp_rate(self.state_[-1]),
                verbose=self.verbose,
                retain=True,
            )

            for i, angle_label in enumerate(self.angles):
                if self.od_normalization_factors[angle_label]:
                    publish(
                        f"morbidostat/{self.unit}/{self.experiment}/od_filtered/{angle_label}",
                        self.state_[i] / self.od_normalization_factors[angle_label],
                        verbose=self.verbose,
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
        subscribe_and_callback(
            self.set_initial_growth_rate, f"morbidostat/{self.unit}/{self.experiment}/growth_rate", timeout=3, max_msgs=1
        )
        subscribe_and_callback(
            self.set_od_normalization_factors,
            f"morbidostat/{self.unit}/{self.experiment}/od_normalization_factors",
            timeout=3,
            max_msgs=1,
        )

        # process incoming data
        subscribe_and_callback(self.update_state_from_observation, f"morbidostat/{self.unit}/{self.experiment}/od_raw_batched")
        subscribe_and_callback(self.update_ekf_variance_after_io_event, f"morbidostat/{self.unit}/{self.experiment}/io_events")

        super(GrowthRateCalculator, self).start_passive_listeners()

    @staticmethod
    def json_to_sorted_dict(json_dict):
        d = json.loads(json_dict)
        return {k: float(d[k]) for k in sorted(d, reverse=True) if not k.startswith("180")}

    @staticmethod
    def create_OD_covariance(angles):
        d = len(angles)
        variances = {"135": 1e-6, "90": 1e-6, "45": 1e-6}

        OD_covariance = 1e-10 * np.ones((d, d))
        for i, a in enumerate(angles):
            for k in variances:
                if a.startswith(k):
                    OD_covariance[i, i] = variances[k]
        return OD_covariance


@log_start(unit, experiment)
@log_stop(unit, experiment)
def growth_rate_calculating(verbose):
    calculator = GrowthRateCalculator(verbose=verbose, unit=unit, experiment=experiment)
    while True:
        signal.pause()


@click.command()
@click.option("--verbose", "-v", count=True, help="Print to std out")
def click_growth_rate_calculating(verbose):
    growth_rate_calculating(verbose)


if __name__ == "__main__":
    click_growth_rate_calculating()
