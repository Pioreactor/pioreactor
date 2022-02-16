# -*- coding: utf-8 -*-
# test_od_reading.py
from __future__ import annotations

import time

import numpy as np
import pytest

from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.background_jobs.od_reading import start_od_reading


def pause() -> None:
    time.sleep(0.25)


def test_sin_regression_exactly() -> None:

    freq = 60
    x = [i / 25 for i in range(25)]
    y = [10 + 2 * np.sin(freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(x, y, freq)
    assert isinstance(A, float)
    assert isinstance(phi, float)
    assert np.abs(C - 10) < 0.1
    assert np.abs(A - 2) < 0.1
    assert np.abs(phi - 0) < 0.1

    freq = 50
    # interestingly, if I used i/25, I get a matrix inversion problem, likely because 25 | 50. This shows the importance of adding a small jitter.
    x = [(i / 25 + 0.001 * (i * 0.618034) % 1) for i in range(25)]
    y = [10 + 2 * np.sin(freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(x, y, freq)
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


def test_ADC_picks_to_correct_freq() -> None:

    actual_freq = 50.0

    x = [i / 25 + 0.005 * np.random.randn() for i in range(25)]
    y = [10 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=["1"])

    best_freq = adc_reader.determine_most_appropriate_AC_hz({"1": x}, {"1": y})
    assert best_freq == actual_freq

    actual_freq = 60.0

    x = [i / 25 + 0.005 * np.random.randn() for i in range(25)]
    y = [2 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=["1"])

    best_freq = adc_reader.determine_most_appropriate_AC_hz({"1": x}, {"1": y})
    assert best_freq == actual_freq


def test_ADC_picks_to_correct_freq_even_if_slight_noise_in_freq() -> None:

    actual_freq = 50.0

    x = [i / 25 + 0.005 * np.random.randn() for i in range(25)]
    y = [
        10 + np.sin((actual_freq + 0.2) * 2 * np.pi * _x) + 0.1 * np.random.randn()
        for _x in x
    ]

    adc_reader = ADCReader(channels=["1"])

    best_freq = adc_reader.determine_most_appropriate_AC_hz({"1": x}, {"1": y})
    assert best_freq == actual_freq


def test_error_thrown_if_wrong_angle() -> None:
    with pytest.raises(ValueError):
        start_od_reading("100", "135", fake_data=True, experiment="test_error_thrown_if_wrong_angle")  # type: ignore

    with pytest.raises(ValueError):
        start_od_reading("100", None, fake_data=True, experiment="test_error_thrown_if_wrong_angle")  # type: ignore

    with pytest.raises(ValueError):
        start_od_reading("135", "99", fake_data=True, experiment="test_error_thrown_if_wrong_angle")  # type: ignore

    with pytest.raises(ValueError):
        start_od_reading("100", "REF", fake_data=True, experiment="test_error_thrown_if_wrong_angle")  # type: ignore

    st = start_od_reading(
        "135", "90", fake_data=True, experiment="test_error_thrown_if_wrong_angle"
    )
    st.set_state(st.DISCONNECTED)


def test_sin_regression_penalizer_C_is_independent_of_scale_of_observed_values() -> None:

    freq = 60
    C_True = 10
    x = [i / 25 for i in range(25)]
    y = [C_True + 2 * np.sin(freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        x, y, freq, prior_C=12, penalizer_C=10.0
    )
    ratio = C / C_True

    # scale everything by 10
    factor = 10
    y = [factor * y_ for y_ in y]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader.sin_regression_with_known_freq(
        x, y, freq, prior_C=factor * 12, penalizer_C=10.0
    )
    assert np.abs(C / (factor * C_True) - ratio) < 0.01
