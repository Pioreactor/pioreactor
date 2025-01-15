# -*- coding: utf-8 -*-
# test_od_calibration
from __future__ import annotations

import numpy as np

from pioreactor.calibrations.utils import calculate_poly_curve_of_best_fit
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.structs import ODCalibration
from pioreactor.utils.timing import current_utc_datetime


def test_linear_data_produces_linear_curve_in_range_even_if_high_degree() -> None:
    od = np.sort(
        np.r_[
            2 ** np.linspace(np.log2(0.5), np.log2(1), num=10),
            2 ** np.linspace(np.log2(0.25), np.log2(0.5), num=10),
            2 ** np.linspace(np.log2(0.125), np.log2(0.25), num=10),
        ]
    )

    od = np.insert(od, 0, 0)
    v = 0.5 * od + 0.01 * np.random.randn(od.shape[0])

    curve_data_ = calculate_poly_curve_of_best_fit(v, od, degree=4)  # type: ignore
    curve_callable = curve_to_callable("poly", curve_data_)
    for od_, v_ in zip(od, curve_callable(od)):
        assert (v_ - od_ * 0.5) < 0.035


def test_mandys_data_for_pathological_poly() -> None:

    od = [0.0, 0.139, 0.155, 0.378, 0.671, 0.993, 1.82, 4.061]
    v = [0.0, 0.0158, 0.0322, 0.0589, 0.1002, 0.1648, 0.4045, 0.5463]

    curve_data_ = calculate_poly_curve_of_best_fit(od, v, degree=3)  # type: ignore
    curve_callable = curve_to_callable("poly", curve_data_)
    assert abs(curve_callable(0.002) - 0.002) < 0.1

    mcal = ODCalibration(
            calibration_name='mandy',
            calibrated_on_pioreactor_unit='pio1',
            created_at=current_utc_datetime(),
            curve_data_=curve_data_,
            curve_type='poly',
            recorded_data={'x': od, 'y': v},
            ir_led_intensity=70.0,
            angle='90',
            pd_channel='2')

    assert abs(mcal.predict(0.002) - curve_callable(0.002)) < 1e-10
    assert abs(mcal.ipredict(0.002) - 0.002) < 0.1





