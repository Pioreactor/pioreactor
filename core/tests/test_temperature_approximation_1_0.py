# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from pioreactor.background_jobs import temperature_automation


class TestTemperatureApproximation_1_0:
    def setup_class(self):
        self.t = temperature_automation.TemperatureAutomationJob

    def test_temperature_approximation_if_less_than_hardcoded_room_temp(self) -> None:
        features = {
            "previous_heater_dc": 0,
            "room_temp": 22.0,
            "time_series_of_temp": [
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
                19.5,
            ],
        }
        assert 19.0 <= self.t.approximate_temperature_20_1_0(features) <= 20.0

    def test_temperature_approximation_if_constant(self) -> None:
        for temp in range(20, 45):
            features = {
                "room_temp": 22.0,
                "previous_heater_dc": 17,
                "time_series_of_temp": 30 * [float(temp)],
            }
            assert abs(temp - self.t.approximate_temperature_20_1_0(features)) < 0.30

    def test_temperature_approximation_even_if_very_tiny_heat_source(self) -> None:
        import numpy as np

        features = {
            "previous_heater_dc": 14.5,
            "room_temp": 22.0,
            "time_series_of_temp": list(
                22 + 10 * np.exp(-0.008 * np.arange(0, 17)) + 0.5 * np.exp(-0.28 * np.arange(0, 17))
            ),
        }

        assert (32 * np.exp(-0.008 * 17)) < self.t.approximate_temperature_20_1_0(features) < 32

    def test_temperature_approximation_even_if_very_large_heat_source(self) -> None:
        import numpy as np

        features = {
            "previous_heater_dc": 14.5,
            "room_temp": 22.0,
            "time_series_of_temp": list(
                22 + 3 * np.exp(-0.008 * np.arange(0, 17)) + 20 * np.exp(-0.28 * np.arange(0, 17))
            ),
        }

        assert (24 * np.exp(-0.008 * 17)) < self.t.approximate_temperature_20_1_0(features) < 25

    def test_temperature_approximation_if_dc_is_nil(self) -> None:
        features = {"previous_heater_dc": 0, "time_series_of_temp": [37.8125, 32.1875]}

        assert self.t.approximate_temperature_20_1_0(features) == 32.1875

    # this is all real data measured insitu, the gold standard.
    def test_temperature_approximation1(self) -> None:
        features = {
            "previous_heater_dc": 64.17342121431545,
            "room_temp": 22.0,
            "time_series_of_temp": [
                48.0,
                45.975,
                44.3875,
                43.05,
                41.9375,
                40.95,
                40.125,
                39.3875,
                38.75,
                38.1875,
                37.6875,
                37.25,
                36.875,
                36.5125,
                36.2125,
                35.9375,
                35.6875,
                35.4625,
                35.25,
                35.0625,
                34.875,
                34.75,
                34.5875,
                34.4875,
                34.3625,
                34.2375,
                34.125,
                34.0,
                33.9375,
            ],
        }

        assert 33.389 <= self.t.approximate_temperature_20_1_0(features) <= 33.830

    def test_temperature_approximation_heating_vial1(self) -> None:
        features = {
            "previous_heater_dc": 69.61390705174689,
            "room_temp": 22.0,
            "time_series_of_temp": [
                49.25,
                47.0375,
                45.3375,
                43.9,
                42.675,
                41.6125,
                40.6875,
                39.9125,
                39.2125,
                38.625,
                38.0875,
                37.625,
                37.1875,
                36.8375,
                36.5,
                36.1875,
                35.9375,
                35.6875,
                35.5,
                35.2625,
                35.125,
                34.9375,
                34.75,
                34.625,
                34.5125,
                34.375,
                34.275,
                34.1875,
                34.075,
            ],
        }

        assert 33.525 <= self.t.approximate_temperature_20_1_0(features) <= 34.00

    def test_temperature_approximation_heating_vial2(self) -> None:
        features = {
            "previous_heater_dc": 73.7259971657559,
            "room_temp": 22.0,
            "time_series_of_temp": [
                50.325,
                47.9875,
                46.175,
                44.65,
                43.375,
                42.25,
                41.3,
                40.4375,
                39.7375,
                39.1125,
                38.525,
                38.0375,
                37.6,
                37.1875,
                36.85,
                36.55,
                36.25,
                36.0,
                35.75,
                35.5625,
                35.375,
                35.2,
                35.0625,
                34.8875,
                34.75,
                34.625,
                34.5125,
                34.425,
                34.3125,
            ],
        }

        assert 33.695 <= self.t.approximate_temperature_20_1_0(features) <= 34.170

    def test_temperature_approximation_heating_vial3(self) -> None:
        features = {
            "previous_heater_dc": 76.6773909437918,
            "room_temp": 22.0,
            "time_series_of_temp": [
                51.25,
                48.7875,
                46.9,
                45.3,
                43.9625,
                42.8125,
                41.8125,
                40.95,
                40.1875,
                39.5625,
                38.9375,
                38.4375,
                37.9625,
                37.5625,
                37.1875,
                36.875,
                36.5625,
                36.3125,
                36.0625,
                35.8625,
                35.625,
                35.475,
                35.3125,
                35.1375,
                35.0,
                34.875,
                34.75,
                34.6875,
                34.5625,
            ],
        }

        assert 33.898 <= self.t.approximate_temperature_20_1_0(features) <= 34.339

    def test_temperature_approximation_heating_vial4(self) -> None:
        features = {
            "previous_heater_dc": 78.4893756629559,
            "room_temp": 22.0,
            "time_series_of_temp": [
                51.875,
                49.375,
                47.45,
                45.8125,
                44.4375,
                43.2625,
                42.25,
                41.375,
                40.575,
                39.8875,
                39.3125,
                38.7625,
                38.3125,
                37.875,
                37.5,
                37.1875,
                36.875,
                36.625,
                36.3625,
                36.1375,
                35.9375,
                35.75,
                35.5875,
                35.4375,
                35.3125,
                35.1875,
                35.0375,
                34.9375,
                34.8125,
            ],
        }

        assert 34.068 <= self.t.approximate_temperature_20_1_0(features) <= 34.577

    def test_temperature_approximation_heating_vial5(self) -> None:
        features = {
            "previous_heater_dc": 79.73052705841252,
            "room_temp": 22.0,
            "time_series_of_temp": [
                52.375,
                49.85,
                47.8875,
                46.25,
                44.85,
                43.65,
                42.6,
                41.6875,
                40.9375,
                40.225,
                39.625,
                39.0625,
                38.625,
                38.1875,
                37.8125,
                37.4625,
                37.175,
                36.875,
                36.625,
                36.375,
                36.1875,
                36.0,
                35.8125,
                35.675,
                35.5,
                35.375,
                35.25,
                35.125,
                35.0,
            ],
        }

        assert 34.305 <= self.t.approximate_temperature_20_1_0(features) <= 34.814

    def test_temperature_approximation6(self) -> None:
        features = {
            "previous_heater_dc": 79.6520681292682,
            "room_temp": 22.0,
            "time_series_of_temp": [
                52.5625,
                50.075,
                48.0875,
                46.4625,
                45.0625,
                43.85,
                42.8125,
                41.9125,
                41.1125,
                40.425,
                39.8125,
                39.25,
                38.775,
                38.3375,
                37.9375,
                37.625,
                37.3125,
                37.0125,
                36.75,
                36.55,
                36.3125,
                36.125,
                35.9375,
                35.8125,
                35.625,
                35.5,
                35.375,
                35.25,
                35.1375,
            ],
        }

        assert 34.475 <= self.t.approximate_temperature_20_1_0(features) <= 35.018

    def test_temperature_approximation7(self) -> None:
        features = {
            "previous_heater_dc": 80.52863053580612,
            "room_temp": 22.0,
            "time_series_of_temp": [
                52.9375,
                50.4,
                48.3875,
                46.7375,
                45.3125,
                44.1125,
                43.05,
                42.1375,
                41.3375,
                40.6375,
                40.0,
                39.5,
                38.9875,
                38.5625,
                38.175,
                37.8125,
                37.5,
                37.2125,
                36.95,
                36.75,
                36.5,
                36.3125,
                36.125,
                36.0,
                35.8125,
                35.6875,
                35.5625,
                35.4375,
                35.3125,
            ],
        }

        assert 34.644 <= self.t.approximate_temperature_20_1_0(features) <= 35.153

    def test_temperature_approximation8(self) -> None:
        features = {
            "previous_heater_dc": 79.91016551185272,
            "room_temp": 22.0,
            "time_series_of_temp": [
                52.9375,
                50.4,
                48.4125,
                46.775,
                45.375,
                44.175,
                43.125,
                42.2125,
                41.4375,
                40.7125,
                40.125,
                39.5625,
                39.0875,
                38.6625,
                38.25,
                37.925,
                37.6125,
                37.3125,
                37.0625,
                36.8125,
                36.625,
                36.4375,
                36.25,
                36.0625,
                35.9375,
                35.775,
                35.625,
                35.5125,
                35.4375,
            ],
        }

        assert 34.746 <= self.t.approximate_temperature_20_1_0(features) <= 35.289

    def test_temperature_approximation9(self) -> None:
        features = {
            "previous_heater_dc": 79.46424847541081,
            "room_temp": 22.0,
            "time_series_of_temp": [
                52.9375,
                50.4125,
                48.45,
                46.8,
                45.4125,
                44.1875,
                43.15,
                42.25,
                41.4375,
                40.7375,
                40.125,
                39.6125,
                39.125,
                38.6875,
                38.3125,
                37.9375,
                37.65,
                37.375,
                37.125,
                36.875,
                36.6875,
                36.5,
                36.3125,
                36.175,
                36.0,
                35.875,
                35.75,
                35.625,
                35.5,
            ],
        }
        assert 34.848 <= self.t.approximate_temperature_20_1_0(features) <= 35.391

    def test_temperature_approximation10(self) -> None:
        features = {
            "previous_heater_dc": 79.69277485968101,
            "room_temp": 22.0,
            "time_series_of_temp": [
                53.0625,
                50.575,
                48.6,
                46.9625,
                45.5625,
                44.35,
                43.3125,
                42.375,
                41.6125,
                40.9125,
                40.3,
                39.7375,
                39.2625,
                38.825,
                38.4375,
                38.1125,
                37.8125,
                37.5,
                37.25,
                37.0375,
                36.8125,
                36.625,
                36.4375,
                36.3125,
                36.125,
                36.0,
                35.875,
                35.75,
                35.625,
            ],
        }

        assert 34.950 <= self.t.approximate_temperature_20_1_0(features) <= 35.493

    def test_temperature_approximation20(self) -> None:
        features = {
            "previous_heater_dc": 79.69277485968101,
            "room_temp": 22.0,
            "time_series_of_temp": [
                53.0625,
                50.575,
                48.6,
                46.9625,
                45.5625,
                44.35,
                43.3125,
                42.375,
                41.6125,
                40.9125,
                40.3,
                39.7375,
                39.2625,
                38.825,
                38.4375,
                38.1125,
                37.8125,
                37.5,
                37.25,
                37.0375,
                36.8125,
                36.625,
                36.4375,
                36.3125,
                36.125,
                36.0,
                35.875,
                35.75,
                35.625,
            ],
        }

        assert 34.950 <= self.t.approximate_temperature_20_1_0(features) <= 35.493

    @pytest.mark.xfail
    def test_temperature_approximation_cooling1(self) -> None:
        features = {
            "previous_heater_dc": 18.05247101728979,
            "room_temp": 22.0,
            "time_series_of_temp": [
                36.625,
                36.05,
                35.5625,
                35.175,
                34.8125,
                34.5625,
                34.25,
                34.0625,
                33.8375,
                33.6875,
                33.5,
                33.375,
                33.25,
                33.125,
                33.025,
                32.9375,
                32.8125,
                32.75,
                32.6875,
                32.625,
                32.5625,
                32.5,
                32.4375,
                32.375,
                32.3125,
                32.275,
                32.225,
                32.1875,
                32.1375,
            ],
        }

        assert 32.169 <= self.t.approximate_temperature_20_1_0(features)

    def test_temperature_approximation_cooling2(self) -> None:
        features = {
            "previous_heater_dc": 13.939849426226885,
            "room_temp": 22.0,
            "time_series_of_temp": [
                34.9375,
                34.4875,
                34.125,
                33.8125,
                33.5,
                33.3125,
                33.0875,
                32.9375,
                32.75,
                32.625,
                32.5125,
                32.4125,
                32.3125,
                32.2,
                32.125,
                32.0625,
                32.0,
                31.9375,
                31.875,
                31.8125,
                31.75,
                31.6875,
                31.6875,
                31.625,
                31.575,
                31.5625,
                31.5,
                31.5,
                31.4375,
            ],
        }

        assert 31.118 <= self.t.approximate_temperature_20_1_0(features)

    def test_temperature_approximation11(self) -> None:
        features = {
            "previous_heater_dc": 12.076511548278965,
            "room_temp": 22.0,
            "time_series_of_temp": [
                32.7625,
                32.375,
                32.0625,
                31.8,
                31.5625,
                31.375,
                31.1875,
                31.0375,
                30.9125,
                30.775,
                30.6875,
                30.5625,
                30.5,
                30.4125,
                30.3625,
                30.2625,
                30.25,
                30.1875,
                30.125,
                30.0625,
                30.05,
                30.0,
                29.9625,
                29.9375,
                29.8875,
                29.875,
                29.85,
                29.8125,
                29.8125,
            ],
        }

        assert 29.628 <= self.t.approximate_temperature_20_1_0(features) <= 30.136

    def test_temperature_approximation12(self) -> None:
        features = {
            "previous_heater_dc": 21.144743904487548,
            "room_temp": 22.0,
            "time_series_of_temp": [
                33.625,
                32.95,
                32.4375,
                31.9625,
                31.5875,
                31.25,
                30.9625,
                30.7,
                30.5,
                30.3125,
                30.125,
                30.0,
                29.875,
                29.75,
                29.6375,
                29.5625,
                29.475,
                29.3875,
                29.3125,
                29.2625,
                29.1875,
                29.1625,
                29.125,
                29.0625,
                29.0,
                29.0,
                28.9375,
                28.925,
                28.875,
            ],
        }

        assert 28.476 <= self.t.approximate_temperature_20_1_0(features) <= 28.747

    def test_temperature_approximation13(self) -> None:
        features = {
            "previous_heater_dc": 23.953722318306838,
            "room_temp": 22.0,
            "time_series_of_temp": [
                34.1875,
                33.3875,
                32.8,
                32.3125,
                31.8625,
                31.5,
                31.1875,
                30.875,
                30.6375,
                30.4375,
                30.25,
                30.0625,
                29.9375,
                29.8,
                29.6875,
                29.5625,
                29.5,
                29.375,
                29.3125,
                29.25,
                29.1875,
                29.125,
                29.0625,
                29.0,
                29.0,
                28.9375,
                28.875,
                28.8625,
                28.8125,
            ],
        }

        assert 28.374 <= self.t.approximate_temperature_20_1_0(features) <= 28.645

    def test_temperature_approximation14(self) -> None:
        features = {
            "previous_heater_dc": 26.28836692713976,
            "room_temp": 22.0,
            "time_series_of_temp": [
                34.625,
                33.7875,
                33.125,
                32.5625,
                32.1,
                31.6875,
                31.3625,
                31.0625,
                30.8125,
                30.5625,
                30.375,
                30.1875,
                30.0125,
                29.875,
                29.75,
                29.625,
                29.525,
                29.4375,
                29.3375,
                29.2625,
                29.1875,
                29.125,
                29.0625,
                29.0,
                28.975,
                28.925,
                28.875,
                28.8125,
                28.8125,
            ],
        }

        assert 28.374 <= self.t.approximate_temperature_20_1_0(features) <= 28.578

    def test_temperature_approximation15(self) -> None:
        features = {
            "previous_heater_dc": 38.129855104856986,
            "room_temp": 22.0,
            "time_series_of_temp": [
                37.6875,
                36.4625,
                35.5125,
                34.7,
                34.0375,
                33.4375,
                32.9375,
                32.5,
                32.1125,
                31.7875,
                31.5,
                31.2375,
                31.0,
                30.8,
                30.625,
                30.45,
                30.3125,
                30.1875,
                30.0625,
                29.9375,
                29.875,
                29.7625,
                29.6875,
                29.625,
                29.5625,
                29.5,
                29.425,
                29.375,
                29.3125,
            ],
        }
        assert 28.815 <= self.t.approximate_temperature_20_1_0(features) <= 29.119

    @pytest.mark.xfail
    def test_temperature_approximation16(self) -> None:
        features = {
            "previous_heater_dc": 18.156877790712812,
            "room_temp": 22.0,
            "time_series_of_temp": [
                29.625,
                29.0625,
                28.6125,
                28.225,
                27.8875,
                27.625,
                27.375,
                27.1875,
                27.0,
                26.825,
                26.6875,
                26.5625,
                26.4375,
                26.325,
                26.25,
                26.1875,
                26.125,
                26.05,
                26.0,
                25.9375,
                25.8875,
                25.875,
                25.8125,
                25.7875,
                25.75,
                25.725,
                25.6875,
                25.6875,
                25.625,
            ],
        }

        assert 25.261 <= self.t.approximate_temperature_20_1_0(features) <= 25.430

    @pytest.mark.xfail
    def test_temperature_approximation17(self) -> None:
        features = {
            "previous_heater_dc": 18.518440157554934,
            "room_temp": 22.0,
            "time_series_of_temp": [
                29.75,
                29.1875,
                28.7125,
                28.3125,
                28.0,
                27.6875,
                27.475,
                27.25,
                27.0625,
                26.925,
                26.7625,
                26.625,
                26.55,
                26.4375,
                26.3125,
                26.25,
                26.1875,
                26.125,
                26.0625,
                26.0,
                25.9875,
                25.9375,
                25.875,
                25.8625,
                25.8125,
                25.8125,
                25.75,
                25.725,
                25.6875,
            ],
        }

        assert 25.295 <= self.t.approximate_temperature_20_1_0(features) <= 25.430

    def test_temperature_approximation21(self) -> None:
        # this was real data from a user

        ts_of_temps = [
            28.6875,
            27.75,
            27.0,
            26.375,
            25.825,
            25.375,
            25.0,
            24.625,
            24.3125,
            24.05,
            23.7875,
            23.5625,
            23.375,
            23.1875,
            23.025,
            22.875,
            22.75,
            22.625,
            22.5,
            22.4375,
            22.3125,
            22.25,
            22.1875,
            22.1125,
            22.0,
            21.95,
            21.9125,
            21.85,
            21.8125,
        ]

        with pytest.raises(ValueError):
            features = {"previous_heater_dc": 25.0, "room_temp": 22.0, "time_series_of_temp": ts_of_temps}
            self.t.approximate_temperature_20_1_0(features)

        better_room_temp = 20
        features = {
            "previous_heater_dc": 25.0,
            "room_temp": better_room_temp,
            "time_series_of_temp": ts_of_temps,
        }

        assert better_room_temp < self.t.approximate_temperature_20_1_0(features) <= 25

    def test_temperature_approximation19(self) -> None:
        # this was real data from a user
        features = {
            "previous_heater_dc": 1.3,
            "room_temp": 22.0,
            "time_series_of_temp": [
                56.4375,
                56.375,
                56.3125,
                56.302083333333336,
                56.25,
                56.25,
                56.1875,
                56.1875,
                56.177083333333336,
                56.135416666666664,
                56.125,
                56.125,
                56.104166666666664,
                56.083333333333336,
                56.0625,
                56.0625,
                56.0625,
                56.0625,
                56.0625,
                56.041666666666664,
                56.052083333333336,
                56.020833333333336,
                56.0,
                56.0,
                56.0,
                56.0,
                56.0,
                56.0,
                56.0,
            ],
        }

        assert 55.5 <= self.t.approximate_temperature_20_1_0(features) <= 56.5

    def test_temperature_approximation50(self) -> None:
        # this was real data from a bheit

        features = {
            "previous_heater_dc": 1.3,
            "room_temp": 22.0,
            "time_series_of_temp": [
                27.21875,
                26.23958333,
                25.52083333,
                24.94791667,
                24.45833333,
                24.0625,
                23.73958333,
                23.4375,
                23.1875,
                23.0,
                22.8125,
                22.63541667,
                22.5,
                22.41666667,
                22.3125,
                22.23958333,
                22.13541667,
                22.0625,
                22.0,
                21.98958333,
                21.9375,
                21.875,
                21.85416667,
                21.8125,
                21.80208333,
                21.75,
                21.75,
                21.72916667,
                21.6875,
            ],
        }

        with pytest.raises(ValueError):
            assert 20 <= self.t.approximate_temperature_20_1_0(features) <= 30

        features = {
            "previous_heater_dc": 1.3,
            "room_temp": 22.0 - 3.0,  # here.
            "time_series_of_temp": [
                27.21875,
                26.23958333,
                25.52083333,
                24.94791667,
                24.45833333,
                24.0625,
                23.73958333,
                23.4375,
                23.1875,
                23.0,
                22.8125,
                22.63541667,
                22.5,
                22.41666667,
                22.3125,
                22.23958333,
                22.13541667,
                22.0625,
                22.0,
                21.98958333,
                21.9375,
                21.875,
                21.85416667,
                21.8125,
                21.80208333,
                21.75,
                21.75,
                21.72916667,
                21.6875,
            ],
        }

        assert 20 <= self.t.approximate_temperature_20_1_0(features) <= 30
