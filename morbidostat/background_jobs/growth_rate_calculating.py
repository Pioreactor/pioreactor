# -*- coding: utf-8 -*-
import time
import threading
import json
import subprocess
from statistics import median

import numpy as np

import click
from morbidostat.utils.streaming_calculations import ExtendedKalmanFilter
from morbidostat.pubsub import publish, subscribe
from morbidostat.utils import log_start, log_stop
from morbidostat.whoami import unit, experiment
from morbidostat.config import config, leader_hostname


def json_to_sorted_dict(json_dict):
    d = json.loads(json_dict)
    return {k: float(d[k]) for k in sorted(d, reverse=True) if not k.startswith("180")}


def create_OD_covariance(angles):
    d = len(angles)
    variances = {"135": 1e-6, "90": 1e-6, "45": 1e-6}

    OD_covariance = 1e-10 * np.ones((d, d))
    for i, a in enumerate(angles):
        for k in variances:
            if a.startswith(k):
                OD_covariance[i, i] = variances[k]
    return OD_covariance


def get_initial_rate(experiment, unit):
    """
    This is a hack to use a timeout (not available in paho-mqtt) to
    see if a value is present in the MQTT cache (retained message)

    TODO: this is dangerous and can be hijacked

    """
    command = f'mosquitto_sub -t "morbidostat/{unit}/{experiment}/growth_rate" -W 3 -h {leader_hostname}'
    test_mqtt = subprocess.run([command], shell=True, capture_output=True)
    if test_mqtt.stdout == b"":
        return 0.0
    else:
        return float(test_mqtt.stdout.strip())


def get_od_normalization_factors(experiment, unit):
    """
    This is a hack to use a timeout (not available in paho-mqtt) to
    see if a value is present in the MQTT cache (retained message)

    TODO: this is dangerous and can be hijacked
    """
    command = f'mosquitto_sub -t "morbidostat/{unit}/{experiment}/od_normalization_factors" -W 3 -h {leader_hostname}'
    test_mqtt = subprocess.run([command], shell=True, capture_output=True)
    if test_mqtt.stdout == b"":
        return None
    else:
        return json.loads(test_mqtt.stdout.strip())


@log_start(unit, experiment)
@log_stop(unit, experiment)
def growth_rate_calculating(verbose=0):

    od_reading_rate = float(config["od_sampling"]["samples_per_second"])
    samples_per_minute = 60 * od_reading_rate

    try:
        # pick good initializations
        latest_od = subscribe(f"morbidostat/{unit}/{experiment}/od_raw_batched")
        angles_and_intial_points = json_to_sorted_dict(latest_od.payload)

        # growth rate in MQTT is hourly, convert back to multiplicative
        initial_rate = np.exp(get_initial_rate(experiment, unit) / 60 / samples_per_minute)

        first_N_observations = {angle_label: [] for angle_label in angles_and_intial_points.keys()}
        od_normalization_factors = get_od_normalization_factors(experiment, unit)

        initial_state = np.array([*angles_and_intial_points.values(), initial_rate])
        d = initial_state.shape[0]

        # empirically selected
        initial_covariance = np.block(
            [[1e-5 * np.ones((d - 1, d - 1)), 1e-8 * np.ones((d - 1, 1))], [1e-8 * np.ones((1, d - 1)), 1e-8]]
        )
        OD_process_covariance = create_OD_covariance(angles_and_intial_points.keys())

        # think of rate_process_variance as a weighting between how much do I trust the model (lower value => rate_t = rate_{t-1}) vs how much do I trust the observations
        rate_process_variance = 1e-11
        process_noise_covariance = np.block(
            [[OD_process_covariance, 1e-12 * np.ones((d - 1, 1))], [1e-12 * np.ones((1, d - 1)), rate_process_variance]]
        )
        observation_noise_covariance = 1e-3 * np.eye(d - 1)

        ekf = ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

        counter = 0
        while True:
            msg = subscribe([f"morbidostat/{unit}/{experiment}/od_raw_batched", f"morbidostat/{unit}/{experiment}/io_events"])

            if "od_raw" in msg.topic:
                ekf.update(np.array([*json_to_sorted_dict(msg.payload).values()]))

            elif "io_events" in msg.topic:
                ekf.scale_OD_variance_for_next_n_steps(1e3, 3 * samples_per_minute)
                continue

            # transform the rate, r, into rate per hour: e^{rate * hours}
            publish(
                f"morbidostat/{unit}/{experiment}/growth_rate",
                np.log(ekf.state_[-1]) * 60 * samples_per_minute,
                verbose=verbose,
                retain=True,
            )

            if od_normalization_factors is None:
                for i, angle_label in enumerate(angles_and_intial_points):
                    # this kills me. What I want is a 1d numpy array with string indexing.
                    first_N_observations[angle_label].append(ekf.state_[i])
                if counter == 20:
                    od_normalization_factors = {
                        angle_label: median(first_N_observations[angle_label]) for angle_label in angles_and_intial_points.keys()
                    }
                    publish(
                        f"morbidostat/{unit}/{experiment}/od_normalization_factors",
                        json.dumps(od_normalization_factors),
                        verbose=verbose,
                        retain=True,
                    )

            else:
                for i, angle_label in enumerate(angles_and_intial_points):
                    publish(
                        f"morbidostat/{unit}/{experiment}/od_filtered/{angle_label}",
                        ekf.state_[i] / od_normalization_factors[angle_label],
                        verbose=verbose,
                    )

            counter += 1

            yield

    except Exception as e:
        publish(f"morbidostat/{unit}/{experiment}/error_log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose)
        raise (e)


@click.command()
@click.option("--verbose", "-v", count=True, help="Print to std out")
def click_growth_rate_calculating(verbose):
    calculator = growth_rate_calculating(verbose)
    while True:
        next(calculator)


if __name__ == "__main__":
    click_growth_rate_calculating()
