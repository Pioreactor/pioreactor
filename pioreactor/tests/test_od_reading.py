# -*- coding: utf-8 -*-
# test_od_reading.py

import time
import numpy as np
from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.whoami import get_latest_experiment_name, get_unit_name


def pause():
    time.sleep(0.25)


def test_sin_regression_exactly():

    x = [i / 25 for i in range(25)]
    y = [10 + 2 * np.sin(60 * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(x, y, 60)
    assert np.abs(C - 10) < 0.1
    assert np.abs(A - 2) < 0.1
    assert np.abs(phi - 0) < 0.1
    adc_reader.set_state(adc_reader.DISCONNECTED)


def test_sin_regression_all_zeros_should_return_zeros():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [0] * 25, 60
    )
    assert C == 0
    assert A == 0
    adc_reader.set_state(adc_reader.DISCONNECTED)


def test_sin_regression_constant_should_return_constant():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [1.0] * 25, 60
    )
    assert C == 1.0
    assert A == 0.0
    adc_reader.set_state(adc_reader.DISCONNECTED)


def test_sin_regression_with_linear_change_should_return_close_to_mean():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    y = [i for i in range(25)]

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], y, 60
    )
    assert np.abs(C - np.mean(y)) < 0.001
    adc_reader.set_state(adc_reader.DISCONNECTED)


def test_sin_regression_with_slightly_lower_frequency():
    # https://electronics.stackexchange.com/questions/57878/how-precise-is-the-frequency-of-the-ac-electricity-network
    actual_freq = 59.5

    x = [i / 25 for i in range(25)]
    y = [10 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(x, y, 60)
    assert np.abs(C - 10) < 0.1
    adc_reader.set_state(adc_reader.DISCONNECTED)


def test_sin_regression_with_slightly_higher_frequency_but_correct_freq_has_better_fit():
    # https://electronics.stackexchange.com/questions/57878/how-precise-is-the-frequency-of-the-ac-electricity-network
    actual_freq = 60.5

    x = [i / 25 for i in range(25)]
    y = [10 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C_60, A, phi), aic_60 = adc_reader.sin_regression_with_known_freq(x, y, 60)
    assert np.abs(C_60 - 10) < 0.1

    (C_61, A, phi), aic_61 = adc_reader.sin_regression_with_known_freq(x, y, actual_freq)
    assert aic_61 < aic_60  # lower is better
    adc_reader.set_state(adc_reader.DISCONNECTED)


def test_sin_regression_with_strong_penalizer():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    adc_reader = ADCReader(unit=unit, experiment=experiment, channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [100] * 25, 60, prior_C=125, penalizer_C=1_000_000
    )
    assert abs(C - 125) < 0.01
    adc_reader.set_state(adc_reader.DISCONNECTED)
