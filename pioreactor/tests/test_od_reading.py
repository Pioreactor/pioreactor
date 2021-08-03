# -*- coding: utf-8 -*-
# test_od_reading.py

import time, json
import numpy as np
from pioreactor.background_jobs.od_reading import LinearTemperatureCompensator, ADCReader
from pioreactor.whoami import get_latest_experiment_name, get_unit_name
from pioreactor.pubsub import publish


def pause():
    time.sleep(0.25)


def test_TemperatureCompensator():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    tc = LinearTemperatureCompensator(unit=unit, experiment=experiment)

    assert tc.compensate_od_for_temperature(1.0) == 1.0

    publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        json.dumps({"temperature": 25, "timestamp": "2020-10-01"}),
    )
    pause()
    assert tc.initial_temperature == 25
    assert tc.latest_temperature == 25

    assert tc.compensate_od_for_temperature(1.0) == 1.0

    publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        json.dumps({"temperature": 30, "timestamp": "2020-10-01"}),
    )

    pause()

    # suppose temp increased, but OD stayed the same
    assert tc.compensate_od_for_temperature(1.0) > 1.0


def test_sin_regression_all_zeros_should_return_zeros():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [0] * 25, 60
    )
    assert C == 0
    assert A == 0


def test_sin_regression_constant_should_return_constant():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [1.0] * 25, 60
    )
    assert C == 1.0
    assert A == 0.0


def test_sin_regression_with_linear_change_should_return_close_to_mean():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    y = [i for i in range(25)]

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], y, 60
    )
    assert np.abs(C - np.mean(y)) < 0.001


def test_sin_regression_with_strong_penalizer():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [100] * 25, 60, prior_C=125, penalizer_C=1_000_000
    )
    assert abs(C - 125) < 0.01
