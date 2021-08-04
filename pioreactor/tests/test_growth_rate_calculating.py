# -*- coding: utf-8 -*-
import json
import time
import numpy as np
from numpy.testing import assert_array_equal

from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.stirring import start_stirring
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.pubsub import publish
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config

unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.5)


def create_od_raw_batched_json(channels=None, voltages=None, angles=None, timestamp=None):
    """
    channel is a list, elements from {0, 1, 2, 3}
    raw_signal is a list
    angle is a list, elements from {0, 45, 90, 135, 180}

    """
    d = {"od_raw": {}, "timestamp": timestamp}
    for channel, voltage, angle in zip(channels, voltages, angles):
        d["od_raw"][channel] = {"voltage": voltage, "angle": angle}

    return json.dumps(d)


class TestGrowthRateCalculating:
    @classmethod
    def setup_class(cls):
        publish(
            f"pioreactor/{unit}/{experiment}/od_blank/mean",
            None,
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            None,
            retain=True,
        )

    def test_subscribing(self):

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            json.dumps({0: 1, 1: 1}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps({0: 1, 1: 1}),
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "0"], [0.9, 1.1], ["135", "90"], timestamp="2010-01-01 12:00:00"
            ),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 1.0, "timestamp": "2010-01-01 12:00:00"}),
            retain=True,
        )
        calc = GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()
        assert calc.initial_growth_rate == 1.0

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [1.12, 0.88], ["90", "135"], timestamp="2010-01-01 12:00:05"
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "0"], [0.87, 1.14], ["135", "90"], timestamp="2010-01-01 12:00:05"
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "0"], [0.85, 1.16], ["135", "90"], timestamp="2010-01-01 12:00:05"
            ),
        )
        pause()

        assert calc.ekf is not None

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [1.14, 0.92], ["90", "135"], timestamp="2010-01-01 12:00:10"
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            '{"volume_change": "1.5", "event": "add_media", "source_of_event": "test"}',
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [1.15, 0.93], ["90", "135"], timestamp="2010-01-01 12:00:15"
            ),
        )

        pause()

        assert calc.state_ is not None

    def test_restart(self):
        publish(
            f"pioreactor/{unit}/{experiment}/od_blank/mean",
            None,
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            '{"0": 1, "1": 1, "2": 1}',
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            '{"0": 1, "1": 1, "2": 1}',
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1", "2"],
                [1.15, 0.93, 1.0],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:15",
            ),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            '{"0": 1.15, "1": 0.93, "2": 1.0}',
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            '{"0": 1, "1": 1, "2": 1}',
            retain=True,
        )

        pause()
        calc1 = GrowthRateCalculator(unit=unit, experiment=experiment)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1", "2"],
                [1.151, 0.931, 1.1],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:20",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1", "2"],
                [1.152, 0.932, 1.2],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:25",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1", "2"],
                [1.153, 0.933, 1.3],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:30",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1", "2"],
                [1.154, 0.934, 1.4],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:35",
            ),
        )
        pause()

        assert calc1.state_[-1] != 0

        calc2 = GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()
        assert calc2.initial_growth_rate != 0

    def test_single_observation(self):
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            '{"0": 1}',
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            '{"0": 1}',
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0"], [1.153], ["90"], timestamp="2010-01-01 12:00:30"
            ),
            retain=True,
        )

        GrowthRateCalculator(unit=unit, experiment=experiment)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0"], [1.155], ["90"], timestamp="2010-01-01 12:00:35"
            ),
        )
        pause()

        assert True

    def test_scaling_works(self):

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            json.dumps({"0": 0.5, "1": 0.8}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps({"0": 1e-6, "1": 1e-4}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01 12:00:35"
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        pause()
        assert calc.od_normalization_factors == {"1": 0.8, "0": 0.5}

    def test_mapping_between_channel_and_angles(self):

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            json.dumps({"0": 0.5, "1": 0.8}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps({"0": 1e-6, "1": 1e-4}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"],
                [0.5, 0.8],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:00:35",
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        pause()
        assert calc.channels_and_angles == {"0": "90,90", "1": "135,45"}

    def test_shock_from_dosing_works(self):

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            json.dumps({"0": 0.5, "1": 0.8}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps({"0": 8.2e-07, "1": 8.2e-07}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"],
                [0.5, 0.8],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:00:35",
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"],
                [0.51, 0.82],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:00:40",
            ),
        )
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"],
                [0.51, 0.82],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:00:45",
            ),
        )
        pause()

        previous_covariance_matrix = calc.ekf.covariance_.copy()

        # trigger dosing events, which change the "regime"
        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            json.dumps(
                {"source_of_event": "algo", "event": "add_media", "volume_change": 1.0}
            ),
        )
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"],
                [0.49, 0.80],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:00:50",
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"],
                [0.48, 0.80],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:00:55",
            ),
        )
        pause()

        assert not np.array_equal(previous_covariance_matrix, calc.ekf.covariance_)

        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            json.dumps(
                {"source_of_event": "algo", "event": "add_media", "volume_change": 1.0}
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"],
                [0.40, 0.70],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:01:00",
            ),
        )
        pause()

        time.sleep(55)
        assert calc.ekf._currently_scaling_covariance
        assert not np.array_equal(previous_covariance_matrix, calc.ekf.covariance_)

        time.sleep(5)
        pause()
        # should revert back
        assert not calc.ekf._currently_scaling_covariance
        assert_array_equal(calc.ekf.covariance_, previous_covariance_matrix)

    def test_end_to_end(self):

        exp = "experiment"
        unit = "unit"
        interval = 0.1
        config["od_config.od_sampling"]["samples_per_second"] = "0.2"

        publish(
            f"pioreactor/{unit}/{exp}/growth_rate_calculating/growth_rate",
            None,
            retain=True,
        )
        publish(f"pioreactor/{unit}/{exp}/od_normalization/mean", None, retain=True)
        publish(f"pioreactor/{unit}/{exp}/od_normalization/variance", None, retain=True)

        start_od_reading(
            *["135", "90", None, None],
            sampling_rate=interval,
            unit=unit,
            experiment=exp,
            fake_data=True,
        )

        start_stirring(duty_cycle=50, unit=unit, experiment=exp)

        calc = GrowthRateCalculator(unit=unit, experiment=exp)

        time.sleep(35)
        assert calc.ekf.state_[-2] != 1.0

    def test_od_blank_being_non_zero(self):

        publish(
            f"pioreactor/{unit}/{experiment}/od_blank/mean",
            json.dumps({"0": 0.25, "1": 0.4}),
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            json.dumps({"0": 0.5, "1": 0.8}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps({"0": 1e-6, "1": 1e-4}),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        pause()
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [0.50, 0.80], ["90", "135"], timestamp="2010-01-01 12:01:00"
            ),
            retain=True,
        )

        pause()
        pause()

        assert calc.od_normalization_factors == {"1": 0.8, "0": 0.5}
        assert calc.od_blank == {"1": 0.4, "0": 0.25}
        results = calc.scale_raw_observations({"1": 1.0, "0": 0.6})
        assert abs(results["1"] - 1.5) < 0.00001
        assert abs(results["0"] - 1.4) < 0.00001

    def test_od_blank_being_higher_than_observations(self):

        publish(
            f"pioreactor/{unit}/{experiment}/od_blank/mean",
            json.dumps({"0": 0.25, "1": 0.4}),
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            json.dumps({"0": 0.5, "1": 0.8}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps({"0": 1e-6, "1": 1e-4}),
            retain=True,
        )

        GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()

        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [0.50, 0.80], ["90", "135"], timestamp="2010-01-01 12:01:00"
            ),
            retain=True,
        )
        pause()
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [0.1, 0.1], ["90", "135"], timestamp="2010-01-01 12:01:05"
            ),
            retain=True,
        )
        pause()
        pause()
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [0.1, 0.1], ["90", "135"], timestamp="2010-01-01 12:01:10"
            ),
            retain=True,
        )
        pause()
        pause()

    def test_od_blank_being_empty(self):

        publish(f"pioreactor/{unit}/{experiment}/od_blank/mean", None, retain=True)

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            json.dumps({"0": 0.5, "1": 0.8}),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            json.dumps({"0": 1e-6, "1": 1e-4}),
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01 12:01:10"
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()

        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["0", "1"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01 12:01:15"
            ),
            retain=True,
        )
        pause()
        pause()
        assert calc.od_normalization_factors == {"1": 0.8, "0": 0.5}
        assert calc.od_blank == {"1": 0.0, "0": 0.0}
        results = calc.scale_raw_observations({"1": 1.0, "0": 0.6})
        assert abs(results["1"] - 1.25) < 0.00001
        assert abs(results["0"] - 1.2) < 0.00001

    def test_observation_order_is_preserved_in_job(monkeypatch):

        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/mean",
            '{"0": 2, "1": 1}',
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_normalization/variance",
            '{"0": 1, "1": 1}',
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "0"], [0.9, 1.1], ["135", "90"], timestamp="2010-01-01 12:00:00"
            ),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 1.0, "timestamp": "2010-01-01 12:00:00"}),
            retain=True,
        )
        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        assert calc.scale_raw_observations({"1": 2, "0": 0.5}) == {"1": 2.0, "0": 0.25}
