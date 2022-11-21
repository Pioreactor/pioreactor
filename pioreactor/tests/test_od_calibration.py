# -*- coding: utf-8 -*-
# test_od_calibration
from __future__ import annotations

import numpy as np

from pioreactor.actions.od_calibration import calculate_curve_of_best_fit
from pioreactor.actions.od_calibration import curve_to_callable


def test_linear_data_produces_linear_curve_in_range_even_if_high_degree():

    od = np.sort(
        np.r_[
            2 ** np.linspace(np.log2(0.5), np.log2(1), num=10),
            2 ** np.linspace(np.log2(0.25), np.log2(0.5), num=10),
            2 ** np.linspace(np.log2(0.125), np.log2(0.25), num=10),
        ]
    )

    od = np.insert(od, 0, 0)

    v = 0.5 * od + 0.01 * np.random.randn(od.shape[0])

    curve_data_, curve_type = calculate_curve_of_best_fit(v, od, degree=4)
    curve_callable = curve_to_callable(curve_type, curve_data_)
    for od_, v_ in zip(od, curve_callable(od)):
        assert (v_ - od_ * 0.5) < 0.035
