# -*- coding: utf-8 -*-
import time
import threading
import json
import os
import subprocess
from statistics import median

import numpy as np

import click
from morbidostat.utils.streaming_calculations import ExtendedKalmanFilter
from morbidostat.pubsub import publish, subscribe
from morbidostat.utils import log_start, log_stop
from morbidostat.whoami import unit, experiment
from morbidostat.config import config, leader_hostname
from morbidostat.background_jobs import BackgroundJob

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


"""
Here's what I should do with this class.
    Make it a thin wrapper around EKF.
    The class listens to the topics (ind.) in the background, and publishes from there
    The threads update the state variable / EKF.


"""


class GrowthRateCalculator(BackgroundJob):

    publish_out = []

    def __init__(self, unit, experiment, verbose=0):
        super(GrowthRateCalculator, self).__init__(job_name=JOB_NAME, verbose=verbose, unit=unit, experiment=experiment)
        self.start_passive_listeners()

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

    def get_initial_rate(self):
        """
        This is a hack to use a timeout (not available in paho-mqtt) to
        see if a value is present in the MQTT cache (retained message)

        TODO: this is dangerous and can be hijacked

        """
        command = f'mosquitto_sub -t "morbidostat/{self.unit}/{self.experiment}/growth_rate" -W 3 -h {leader_hostname}'
        test_mqtt = subprocess.run([command], shell=True, capture_output=True, universal_output=True)
        if test_mqtt.stdout == "":
            return 0.0
        else:
            return float(test_mqtt.stdout.strip())

    def get_od_normalization_factors(self, desired_angles):
        """
        This is a hack to use a timeout (not available in paho-mqtt) to
        see if a value is present in the MQTT cache (retained message)

        TODO: this is dangerous and can be hijacked
        """
        command = (
            f'mosquitto_sub -t "morbidostat/{self.unit}/{self.experiment}/od_normalization_factors" -W 3 -h {leader_hostname}'
        )
        test_mqtt = subprocess.run([command], shell=True, capture_output=True, universal_output=True)
        if test_mqtt.stdout == "":
            return None
        else:
            propsed_factors = json.loads(test_mqtt.stdout.strip())
            for angle in desired_angles:
                if angle not in propsed_factors:
                    return None
            return propsed_factors

    def run(self):

        od_reading_rate = float(config["od_sampling"]["samples_per_second"])
        samples_per_minute = 60 * od_reading_rate

        try:
            # pick good initializations
            latest_od = subscribe(f"morbidostat/{self.unit}/{self.experiment}/od_raw_batched")
            angles_and_intial_points = self.json_to_sorted_dict(latest_od.payload)
            print("here1")

            # growth rate in MQTT is hourly, convert back to multiplicative
            initial_rate = np.exp(self.get_initial_rate() / 60 / samples_per_minute)

            first_N_observations = {angle_label: [] for angle_label in angles_and_intial_points.keys()}
            od_normalization_factors = self.get_od_normalization_factors(angles_and_intial_points.keys())

            initial_state = np.array([*angles_and_intial_points.values(), initial_rate])
            d = initial_state.shape[0]

            # empirically selected
            initial_covariance = np.block(
                [[1e-5 * np.ones((d - 1, d - 1)), 1e-8 * np.ones((d - 1, 1))], [1e-8 * np.ones((1, d - 1)), 1e-8]]
            )
            OD_process_covariance = self.create_OD_covariance(angles_and_intial_points.keys())

            # think of rate_process_variance as a weighting between how much do I trust the model (lower value => rate_t = rate_{t-1}) vs how much do I trust the observations
            rate_process_variance = 1e-10
            process_noise_covariance = np.block(
                [[OD_process_covariance, 1e-12 * np.ones((d - 1, 1))], [1e-12 * np.ones((1, d - 1)), rate_process_variance]]
            )
            observation_noise_covariance = 1e-3 * np.eye(d - 1)

            ekf = ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

            counter = 0
            while self.active:
                print("here2")
                msg = subscribe(
                    [
                        f"morbidostat/{self.unit}/{self.experiment}/od_raw_batched",
                        f"morbidostat/{self.unit}/{self.experiment}/io_events",
                    ]
                )

                if "od_raw" in msg.topic:
                    ekf.update(np.array([*self.json_to_sorted_dict(msg.payload).values()]))

                elif "io_events" in msg.topic:
                    ekf.scale_OD_variance_for_next_n_steps(5e3, 2 * samples_per_minute)
                    continue
                print("here3")

                # transform the rate, r, into rate per hour: e^{rate * hours}
                publish(
                    f"morbidostat/{self.unit}/{self.experiment}/growth_rate",
                    np.log(ekf.state_[-1]) * 60 * samples_per_minute,
                    verbose=self.verbose,
                    retain=True,
                )

                if od_normalization_factors is None:
                    for i, angle_label in enumerate(angles_and_intial_points):
                        # this kills me. What I want is a 1d numpy array with string indexing.
                        first_N_observations[angle_label].append(ekf.state_[i])
                    if counter == 20:
                        od_normalization_factors = {
                            angle_label: median(first_N_observations[angle_label])
                            for angle_label in angles_and_intial_points.keys()
                        }
                        publish(
                            f"morbidostat/{self.unit}/{self.experiment}/od_normalization_factors",
                            json.dumps(od_normalization_factors),
                            verbose=self.verbose,
                            retain=True,
                        )

                else:
                    for i, angle_label in enumerate(angles_and_intial_points):
                        publish(
                            f"morbidostat/{self.unit}/{self.experiment}/od_filtered/{angle_label}",
                            ekf.state_[i] / od_normalization_factors[angle_label],
                            verbose=self.verbose,
                        )
                        yield (angle_label, ekf.state_[i] / od_normalization_factors[angle_label])

                counter += 1

        except Exception as e:
            publish(
                f"morbidostat/{self.unit}/{self.experiment}/error_log", f"[{JOB_NAME}]: failed {str(e)}", verbose=self.verbose
            )
            raise (e)


@log_start(unit, experiment)
@log_stop(unit, experiment)
def growth_rate_calculating(verbose):
    calculator = GrowthRateCalculator(verbose)
    while True:
        calculator.run()


@click.command()
@click.option("--verbose", "-v", count=True, help="Print to std out")
def click_growth_rate_calculating(verbose):
    growth_rate_calculating(verbose)


if __name__ == "__main__":
    click_growth_rate_calculating()
