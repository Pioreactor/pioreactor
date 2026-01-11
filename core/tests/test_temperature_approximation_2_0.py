# -*- coding: utf-8 -*-
from pioreactor.background_jobs.temperature_automation import TemperatureAutomationJob


class TestTemperatureApproximation_2_0:
    def setup_class(self):
        self.t = TemperatureAutomationJob

    def test_temperature_approximation_if_constant(self) -> None:
        # TODO: we should add some constants like this to the dataset.

        for temp in range(25, 35):
            features = {
                "room_temp": 22.0,
                "previous_heater_dc": 0.001,  # should be nonzero to not short circuit the if previous_heater_dc == 0 line.
                "time_series_of_temp": 21 * [float(temp)],
            }
            assert abs(temp - self.t.approximate_temperature_20_2_0(features)) < 0.30

    def test_temperature_approximation1(self) -> None:
        features = {
            "previous_heater_dc": 45.57,
            "room_temp": 22.0,
            "time_series_of_temp": [
                48.427083333333336,
                46.520833333333336,
                45.208333333333336,
                44.135416666666664,
                43.270833333333336,
                42.552083333333336,
                41.9375,
                41.416666666666664,
                40.958333333333336,
                40.5625,
                40.21875,
                39.9375,
                39.625,
                39.427083333333336,
                39.1875,
                39.0,
                38.8125,
                38.625,
                38.5,
                38.3125,
                38.1875,
            ],
        }
        assert abs(38.9 - self.t.approximate_temperature_20_2_0(features)) < 0.5

    def test_temperature_approximation2(self) -> None:
        features = {
            "previous_heater_dc": 12.53,
            "room_temp": 22.0,
            "time_series_of_temp": [
                35.385416666666664,
                34.864583333333336,
                34.510416666666664,
                34.166666666666664,
                33.84375,
                33.65625,
                33.395833333333336,
                33.21875,
                33.010416666666664,
                32.885416666666664,
                32.770833333333336,
                32.614583333333336,
                32.489583333333336,
                32.364583333333336,
                32.229166666666664,
                32.177083333333336,
                32.114583333333336,
                32.03125,
                31.979166666666668,
                31.927083333333332,
                31.822916666666668,
            ],
        }
        assert abs(31.85 - self.t.approximate_temperature_20_2_0(features)) < 0.5

    def test_temperature_approximation3(self) -> None:
        features = {
            "previous_heater_dc": 46.12,
            "room_temp": 22.0,
            "time_series_of_temp": [
                48.552083333333336,
                46.604166666666664,
                45.270833333333336,
                44.208333333333336,
                43.322916666666664,
                42.59375,
                41.96875,
                41.4375,
                41.0,
                40.604166666666664,
                40.25,
                39.9375,
                39.677083333333336,
                39.4375,
                39.1875,
                39.0,
                38.8125,
                38.625,
                38.5,
                38.3125,
                38.1875,
            ],
        }
        assert abs(38.94220102733567 - self.t.approximate_temperature_20_2_0(features)) < 0.5

    def test_temperature_approximation4(self) -> None:
        features = {
            "previous_heater_dc": 27.31,
            "room_temp": 22.0,
            "time_series_of_temp": [
                42.28125,
                41.1875,
                40.322916666666664,
                39.614583333333336,
                39.010416666666664,
                38.46875,
                37.989583333333336,
                37.583333333333336,
                37.208333333333336,
                36.84375,
                36.59375,
                36.291666666666664,
                36.0625,
                35.791666666666664,
                35.583333333333336,
                35.385416666666664,
                35.197916666666664,
                35.041666666666664,
                34.885416666666664,
                34.75,
                34.625,
            ],
        }
        assert abs(34.1204 - self.t.approximate_temperature_20_2_0(features)) < 0.5

    def test_temperature_approximation5(self) -> None:
        features = {
            "previous_heater_dc": 14.791,
            "room_temp": 22.0,
            "time_series_of_temp": [
                34.75,
                34.1875,
                33.760416666666664,
                33.4375,
                33.1875,
                32.9375,
                32.739583333333336,
                32.5625,
                32.385416666666664,
                32.25,
                32.125,
                32.020833333333336,
                31.9375,
                31.822916666666668,
                31.75,
                31.6875,
                31.625,
                31.5625,
                31.5,
                31.447916666666668,
                31.395833333333332,
            ],
        }
        assert abs(30.94587 - self.t.approximate_temperature_20_2_0(features)) < 0.5
