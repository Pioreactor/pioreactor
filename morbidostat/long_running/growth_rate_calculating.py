import time
import threading

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from paho.mqtt import publish
import paho.mqtt.subscribe as subscribe


import click
from morbidostat.utils.streaming import ExtendedKalmanFilter


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
def growth_rate_calculating(unit):

    initial_state = np.array([1., 1.])
    initial_covariance = np.eye(2)
    process_noise_covariance = np.array([[0.00001, 0], [0, 1e-13]])
    observation_noise_covariance = 0.2
    ekf = ExtendedKalmanFilter(initial_state, initial_covariance, process_noise_covariance, observation_noise_covariance)


    while True:
        msg = subscribe.simple([f"morbidostat/{unit}/od_raw", f"morbidostat/{unit}/io_events"])

        if msg.topic.endswith("od_raw"):
            ekf.update(float(msg.payload))

        elif msg.topic.endswith("io_events"):
            ekf.set_OD_variance_for_next_n_units(0.3, 15)

        print(ekf.state_)


if __name__ == "__main__":
    growth_rate_calculating()
