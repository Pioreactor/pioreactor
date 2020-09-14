import time
import threading

import numpy as np
import paho.mqtt.subscribe as subscribe


import click
from morbidostat.utils.streaming_calculations import ExtendedKalmanFilter
from morbidostat.utils import leader_hostname
from morbidostat.utils.publishing import publish


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--angle", default="135", help="The photodiode angle to use")
@click.option("--verbose", is_flag=True, help="Print to std out")
def growth_rate_calculating(unit, angle, verbose):

    publish(f"morbidostat/{unit}/log", "[growth_rate_calculating]: starting", verbose=verbose)

    try:
        # pick a good initialization
        msg = subscribe.simple([f"morbidostat/{unit}/od_raw/{angle}"], hostname=leader_hostname)
        initial_state = np.array([float(msg.payload), 1.0])

        # empirically picked constants
        initial_covariance = np.array([[1e-3, 0], [0, 1e-8]])
        process_noise_covariance = np.array([[1e-5, 0], [0, 1e-12]])
        observation_noise_covariance = 1.0
        ekf = ExtendedKalmanFilter(
            initial_state,
            initial_covariance,
            process_noise_covariance,
            observation_noise_covariance,
        )

        while True:
            msg = subscribe.simple(
                [f"morbidostat/{unit}/od_raw/{angle}", f"morbidostat/{unit}/io_events"],
                hostname=leader_hostname,
            )

            if "od_raw" in msg.topic:
                ekf.update(float(msg.payload))

            elif "io_events" in msg.topic:
                ekf.set_OD_variance_for_next_n_steps(0.1, 8 * 60)
                continue

            # transform the rate, r, into rate per hour: e^{rate * hours}
            publish(
                f"morbidostat/{unit}/growth_rate",
                np.log(ekf.state_.rate) * 60 * 60,
                verbose=verbose,
            )
            publish(f"morbidostat/{unit}/od_filtered", ekf.state_.OD, verbose=verbose)
    except Exception as e:
        publish(
            f"morbidostat/{unit}/error_log",
            f"[growth_rate_calculating]: failed {str(e)}",
            verbose=verbose,
        )
        publish(
            f"morbidostat/{unit}/log", f"[growth_rate_calculating]: failed {str(e)}", verbose=verbose
        )


if __name__ == "__main__":
    growth_rate_calculating()
