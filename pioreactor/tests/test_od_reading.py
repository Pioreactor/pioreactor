# -*- coding: utf-8 -*-
# test_od_reading.py

import time
import numpy as np
from pioreactor.background_jobs.od_reading import ADCReader


def pause() -> None:
    time.sleep(0.25)


def test_sin_regression_exactly() -> None:

    x = [i / 25 for i in range(25)]
    y = [10 + 2 * np.sin(60 * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(x, y, 60)
    assert isinstance(A, float)
    assert isinstance(phi, float)
    assert np.abs(C - 10) < 0.1
    assert np.abs(A - 2) < 0.1
    assert np.abs(phi - 0) < 0.1


def test_sin_regression_all_zeros_should_return_zeros() -> None:
    import numpy as np

    with np.errstate(all="raise"):
        adc_reader = ADCReader(channels=[])

        (C, A, phi), AIC = adc_reader.sin_regression_with_known_freq(
            [i / 25 for i in range(25)], [0] * 25, 60
        )
        assert C == 0
        assert A == 0
        assert np.isinf(AIC)


def test_sin_regression_constant_should_return_constant() -> None:

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [1.0] * 25, 60
    )
    assert C == 1.0
    assert A == 0.0


def test_sin_regression_with_linear_change_should_return_close_to_mean() -> None:

    adc_reader = ADCReader(channels=[])

    y = [i for i in range(25)]

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], y, 60
    )
    assert np.abs(C - np.mean(y)) < 0.001


def test_sin_regression_with_slightly_lower_frequency() -> None:
    # https://electronics.stackexchange.com/questions/57878/how-precise-is-the-frequency-of-the-ac-electricity-network
    actual_freq = 59.5

    x = [i / 25 for i in range(25)]
    y = [10 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(x, y, 60)
    assert np.abs(C - 10) < 0.1


def test_sin_regression_with_slightly_higher_frequency_but_correct_freq_has_better_fit() -> None:
    # https://electronics.stackexchange.com/questions/57878/how-precise-is-the-frequency-of-the-ac-electricity-network
    actual_freq = 60.5

    x = [i / 25 for i in range(25)]
    y = [10 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C_60, A, phi), aic_60 = adc_reader.sin_regression_with_known_freq(x, y, 60)
    assert np.abs(C_60 - 10) < 0.1

    (C_61, A, phi), aic_61 = adc_reader.sin_regression_with_known_freq(x, y, actual_freq)
    assert aic_61 < aic_60  # lower is better


def test_sin_regression_with_strong_penalizer() -> None:

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [100] * 25, 60, prior_C=125, penalizer_C=1_000_000
    )
    assert abs(C - 125) < 0.01
