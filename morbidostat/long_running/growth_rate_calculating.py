# -*- coding: utf-8 -*-
import time
import threading
import json
import subprocess

import numpy as np

import click
from morbidostat.utils.streaming_calculations import ExtendedKalmanFilter
from morbidostat.utils.pubsub import publish, subscribe
from morbidostat.utils import config, get_unit_from_hostname, get_latest_experiment_name


def json_to_sorted_dict(json_dict):
    d = json.loads(json_dict)
    return {k: float(d[k]) for k in sorted(d, reverse=True)}


def create_OD_covariance(angles):
    d = len(angles)
    variances = {"135": 1e-5, "90": 1e-7}

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

    """
    test_mqtt = subprocess.run(
        [f'mosquitto_sub -t "morbidostat/{unit}/{experiment}/growth_rate" -W 3'], shell=True, capture_output=True
    )
    if test_mqtt.stdout == b"":
        return 0.0
    else:
        return float(test_mqtt.stdout.strip())


def growth_rate_calculating(verbose=False):
    unit = get_unit_from_hostname()
    experiment = get_latest_experiment_name()

    od_reading_rate = float(config["od_sampling"]["samples_per_second"])
    samples_per_minute = 60 * od_reading_rate

    publish(f"morbidostat/{unit}/{experiment}/log", "[growth_rate_calculating]: starting", verbose=verbose)

    try:
        # pick good initializations
        latest_od = subscribe(f"morbidostat/{unit}/{experiment}/od_raw_batched")

        # growth rate in MQTT is hourly, convert back to multiplicative
        initial_rate = np.exp(get_initial_rate(experiment, unit) / 60 / samples_per_minute)

        angles_and_intial_points = json_to_sorted_dict(latest_od.payload)
        initial_state = np.array([*angles_and_intial_points.values(), initial_rate])
        d = initial_state.shape[0]

        # empirically selected
        initial_covariance = np.block(
            [[1e-5 * np.ones((d - 1, d - 1)), 1e-8 * np.ones((d - 1, 1))], [1e-8 * np.ones((1, d - 1)), 1e-8]]
        )
        OD_process_covariance = create_OD_covariance(angles_and_intial_points.keys())

        # think of rate_process_variance as a weighting between how much do I trust the model (lower value => rate_t = rate_{t-1}) vs how much do I trust the observations
        rate_process_variance = 5e-11
        process_noise_covariance = np.block(
            [[OD_process_covariance, 1e-12 * np.ones((d - 1, 1))], [1e-12 * np.ones((1, d - 1)), rate_process_variance]]
        )
        observation_noise_covariance = 1e-3 * np.eye(d - 1)  # TODO: this should be a function of the angle and gain

        ekf = ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

        while True:
            msg = subscribe([f"morbidostat/{unit}/{experiment}/od_raw_batched", f"morbidostat/{unit}/{experiment}/io_events"])

            if "od_raw" in msg.topic:
                ekf.update(np.array([*json_to_sorted_dict(msg.payload).values()]))

            elif "io_events" in msg.topic:
                ekf.scale_OD_variance_for_next_n_steps(1e2, 5 * samples_per_minute)
                continue

            # transform the rate, r, into rate per hour: e^{rate * hours}
            publish(
                f"morbidostat/{unit}/{experiment}/growth_rate",
                np.log(ekf.state_[-1]) * 60 * samples_per_minute,
                verbose=verbose,
                retain=True,
            )

            for i, angle in enumerate(angles_and_intial_points):
                publish(f"morbidostat/{unit}/{experiment}/od_filtered/{angle}", ekf.state_[i], verbose=verbose)

            yield

    except Exception as e:
        publish(f"morbidostat/{unit}/{experiment}/error_log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose)
        publish(f"morbidostat/{unit}/{experiment}/log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose)
        raise (e)


@click.command()
@click.option("--verbose", is_flag=True, help="Print to std out")
def click_growth_rate_calculating(verbose):
    calculator = growth_rate_calculating(verbose)
    while True:
        next(calculator)


if __name__ == "__main__":
    click_growth_rate_calculating()
