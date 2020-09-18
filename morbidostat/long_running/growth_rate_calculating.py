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


def growth_rate_calculating(verbose):
    unit = get_unit_from_hostname()

    publish(f"morbidostat/{unit}/log", "[growth_rate_calculating]: starting", verbose=verbose)

    try:
        # pick a good initialization
        msg = subscribe([f"morbidostat/{unit}/od_raw_batched"])

        angles_and_intial_points = json_to_sorted_dict(msg.payload)
        initial_state = np.array([*angles_and_intial_points.values(), 1.0])
        d = initial_state.shape[0]

        initial_covariance = np.diag([1e-3] * (d - 1) + [1e-8])

        OD_covariance = 1e-6 * np.ones((d - 1, d - 1))
        OD_covariance[np.arange(d - 1), np.arange(d - 1)] = 1e-3
        process_noise_covariance = np.block([[OD_covariance, 1e-9 * np.ones((d - 1, 1))], [1e-9 * np.ones((1, d - 1)), 1e-8]])

        observation_noise_covariance = 1e-4 * np.ones(d - 1)  # this is a function of the ADS resolution at a gain
        ekf = ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)

        while True:
            msg = subscribe([f"morbidostat/{unit}/od_raw_batched", f"morbidostat/{unit}/io_events"])

            if "od_raw" in msg.topic:
                ekf.update([*json_to_sorted_dict(msg.payload).values()])

            elif "io_events" in msg.topic:
                ekf.set_OD_variance_for_next_n_steps(0.1, 8 * 60)
                continue

            # transform the rate, r, into rate per hour: e^{rate * hours}
            od_reading_rate = float(config["od_sampling"]["samples_per_second"])
            publish(f"morbidostat/{unit}/growth_rate", np.log(ekf.state_[-1]) * 60 * 60 * od_reading_rate, verbose=verbose)

            for i, angle in enumerate(angles_and_intial_points):
                publish(f"morbidostat/{unit}/od_filtered/{angle}", ekf.state_[i], verbose=verbose)

    except Exception as e:
        publish(f"morbidostat/{unit}/error_log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose)
        publish(f"morbidostat/{unit}/log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose)
        raise (e)


@click.command()
@click.option("--verbose", is_flag=True, help="Print to std out")
def click_growth_rate_calculating(verbose):
    return growth_rate_calculating(verbose)


if __name__ == "__main__":
    click_growth_rate_calculating()
