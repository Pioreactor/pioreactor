import time
import threading
import json

import numpy as np


import click
from morbidostat.utils.streaming_calculations import ExtendedKalmanFilter
from morbidostat.utils.pubsub import publish, subscribe
from morbidostat.utils import config


def json_to_sorted_dict(json_dict):
    d = json.loads(json_dict)
    return {k: float(d[k]) for k in sorted(d, reverse=True)}


@click.command()
@click.argument("unit")
@click.option("--verbose", is_flag=True, help="Print to std out")
def growth_rate_calculating(unit, verbose):

    publish(f"morbidostat/{unit}/log", "[growth_rate_calculating]: starting", verbose=verbose)

    try:
        # pick a good initialization
        msg = subscribe([f"morbidostat/{unit}/od_raw_batched"])
        angles_and_intial_points = json_to_sorted_dict(msg.payload)
        initial_state = np.array([*angles_and_intial_points.values(), 1.0])
        d = initial_state.shape[0]

        # empirically picked constants
        initial_covariance = np.diag([1e-3] * (d - 1) + [1e-8])
        process_noise_covariance = np.diag([1e-5] * (d - 1) + [1e-12])
        observation_noise_covariance = 1.0
        ekf = ExtendedKalmanFilter(
            initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance,
        )

        while True:
            msg = subscribe([f"morbidostat/{unit}/od_raw_batched", f"morbidostat/{unit}/io_events"])

            if "od_raw" in msg.topic:
                ekf.update([*json_to_sorted_dict(msg.payload).values()])

            elif "io_events" in msg.topic:
                ekf.set_OD_variance_for_next_n_steps(0.1, 8 * 60)
                continue

            # transform the rate, r, into rate per hour: e^{rate * hours}
            od_reading_rate = float(config["od_sampling"]["samples_per_second"])
            publish(
                f"morbidostat/{unit}/growth_rate",
                np.log(ekf.state_[-1]) * 60 * 60 * od_reading_rate,
                verbose=verbose,
            )

            for i, angle in enumerate(angles_and_intial_points):
                publish(f"morbidostat/{unit}/od_filtered/{angle}", ekf.state_[i], verbose=verbose)

    except Exception as e:
        publish(
            f"morbidostat/{unit}/error_log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose,
        )
        publish(
            f"morbidostat/{unit}/log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose,
        )


if __name__ == "__main__":
    growth_rate_calculating()
