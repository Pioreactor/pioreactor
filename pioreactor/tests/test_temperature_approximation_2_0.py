# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.background_jobs import temperature_control


class TestTemperatureApproximation_2_0:
    def setup_class(self):
        self.t = temperature_control.TemperatureController

    def test_temperature_approximation_if_constant(self) -> None:
        # TODO: we should add some constants like this to the dataset.

        for temp in range(20, 45):
            features = {
                "room_temp": 22.0,
                "previous_heater_dc": 10,  # should be nonzero to not short circuit the if previous_heater_dc == 0 line.
                "time_series_of_temp": 21 * [float(temp)],
            }
            assert abs(temp - self.t.approximate_temperature_2_0(features)) < 0.30

    def test_temperature_approximation1(self) -> None:
        features = {
            "previous_heater_dc": 11.52,
            "room_temp": 22.0,
            "time_series_of_temp": [
                32.989583333333336,
                32.520833333333336,
                32.21875,
                31.9375,
                31.75,
                31.5625,
                31.385416666666668,
                31.25,
                31.135416666666668,
                31.010416666666668,
                30.9375,
                30.875,
                30.802083333333332,
                30.71875,
                30.6875,
                30.625,
                30.5625,
                30.510416666666668,
                30.5,
                30.4375,
                30.416666666666668,
            ],
        }
        assert 29.9 <= self.t.approximate_temperature_2_0(features) <= 30.1

    def test_temperature_approximation2(self) -> None:
        features = {
            "previous_heater_dc": 12.14,
            "room_temp": 22.0,
            "time_series_of_temp": [
                33.125,
                32.666666666666664,
                32.3125,
                32.0625,
                31.8125,
                31.625,
                31.4375,
                31.3125,
                31.1875,
                31.0625,
                30.979166666666668,
                30.875,
                30.8125,
                30.75,
                30.6875,
                30.625,
                30.5625,
                30.510416666666668,
                30.479166666666668,
                30.4375,
                30.40625,
            ],
        }
        assert 29.9 <= self.t.approximate_temperature_2_0(features) <= 30.1
