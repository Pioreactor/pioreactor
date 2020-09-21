# -*- coding: utf-8 -*-
import time
import threading
import json

import numpy as np

import click
from morbidostat.utils.streaming_calculations import ExtendedKalmanFilter
from morbidostat.utils.pubsub import publish, subscribe
from morbidostat.utils import config, get_unit_from_hostname


def json_to_sorted_dict(json_dict):
    d = json.loads(json_dict)
    return {k: float(d[k]) for k in sorted(d, reverse=True)}


def create_OD_covariance(angles):
    d = len(angles)
    variances = {"135": 1e-5, "90": 1e-8}

    OD_covariance = 1e-10 * np.ones((d, d))
    for i, a in enumerate(angles):
        for k in variances:
            if a.startswith(k):
                OD_covariance[i, i] = variances[k]
    return OD_covariance


def growth_rate_calculating(verbose=False):
    unit = get_unit_from_hostname()
    od_reading_rate = float(config["od_sampling"]["samples_per_second"])
    samples_per_minute = 60 * od_reading_rate

    publish(f"morbidostat/{unit}/log", "[growth_rate_calculating]: starting", verbose=verbose)

    try:
        # pick a good initialization
        msg = subscribe([f"morbidostat/{unit}/od_raw_batched"])

        angles_and_intial_points = json_to_sorted_dict(msg.payload)
        initial_state = np.array([*angles_and_intial_points.values(), 1.0])
        d = initial_state.shape[0]

        initial_covariance = np.diag([1e-3] * (d - 1) + [1e-8])
        OD_process_covariance = create_OD_covariance(angles_and_intial_points.keys())
        rate_process_variance = (
            1e-13
        )  # think of this as a weighting between how much do I trust the model (lower value => rate_t = rate_{t-1}) vs how much do I trust the observations
        process_noise_covariance = np.block(
            [[OD_process_covariance, 1e-10 * np.ones((d - 1, 1))], [1e-10 * np.ones((1, d - 1)), rate_process_variance]]
        )

        observation_noise_covariance = 1e-4 * np.ones(d - 1)  # this is a function of the ADS resolution at a gain
        ekf = ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

        while True:
            msg = subscribe([f"morbidostat/{unit}/od_raw_batched", f"morbidostat/{unit}/io_events"])

            if "od_raw" in msg.topic:
                ekf.update([*json_to_sorted_dict(msg.payload).values()])

            elif "io_events" in msg.topic:
                ekf.scale_OD_variance_for_next_n_steps(10, 8 * samples_per_minute)
                continue

            # transform the rate, r, into rate per hour: e^{rate * hours}
            publish(f"morbidostat/{unit}/growth_rate", np.log(ekf.state_[-1]) * 60 * samples_per_minute, verbose=verbose)

            for i, angle in enumerate(angles_and_intial_points):
                publish(f"morbidostat/{unit}/od_filtered/{angle}", ekf.state_[i], verbose=verbose)
                yield

    except Exception as e:
        publish(f"morbidostat/{unit}/error_log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose)
        publish(f"morbidostat/{unit}/log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose)
        raise (e)


@click.command()
@click.option("--verbose", is_flag=True, help="Print to std out")
def click_growth_rate_calculating(verbose):
    calculator = growth_rate_calculating(verbose)
    while True:
        next(calculator)


if __name__ == "__main__":
    click_growth_rate_calculating()
