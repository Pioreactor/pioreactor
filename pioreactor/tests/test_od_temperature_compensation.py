# -*- coding: utf-8 -*-
from pioreactor.actions.od_temperature_compensation import simple_linear_regression
import numpy as np


def test_simple_linear_regression_output_vs_statsmodels():
    x = np.array(
        [
            26.875,
            29.25,
            30.4375,
            31.6875,
            32.75,
            34.15625,
            35.59375,
            36.40625,
            37.53125,
            38.09375,
            39.28125,
            40.28125,
            41.34375,
        ]
    )
    y = np.array(
        [
            -1.37724141,
            -1.4135525,
            -1.43125456,
            -1.44784476,
            -1.45474955,
            -1.46601597,
            -1.47830033,
            -1.47780077,
            -1.48379809,
            -1.49380208,
            -1.49613921,
            -1.49285728,
            -1.49295402,
        ]
    )

    (m, std_m), (b, std_b) = simple_linear_regression(x, y)

    assert np.abs(m - -0.0077) < 0.001
    assert np.abs(std_m - 0.0008) < 0.001
    assert np.abs(b - -1.1932) < 0.001
    assert np.abs(std_b - 0.0265) < 0.001
