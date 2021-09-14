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
from pioreactor.utils import local_persistant_storage

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
        assert int(channel) in [0, 1, 2, 3]
        d["od_raw"][channel] = {"voltage": voltage, "angle": angle}

    return json.dumps(d)


class TestGrowthRateCalculating:
    @classmethod
    def setup_class(cls):
        # clear the caches and MQTT

        with local_persistant_storage("od_blank") as cache:
            if experiment in cache:
                del cache[experiment]

        with local_persistant_storage("od_normalization_mean") as cache:
            if experiment in cache:
                del cache[experiment]

        with local_persistant_storage("od_normalization_variance") as cache:
            if experiment in cache:
                del cache[experiment]

        publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            None,
            retain=True,
        )

    def test_subscribing(self):

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["2", "1"], [0.9, 1.1], ["135", "90"], timestamp="2010-01-01 12:00:00"
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
                ["1", "2"], [1.12, 0.88], ["90", "135"], timestamp="2010-01-01 12:00:05"
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["2", "1"], [0.87, 1.14], ["135", "90"], timestamp="2010-01-01 12:00:05"
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["2", "1"], [0.85, 1.16], ["135", "90"], timestamp="2010-01-01 12:00:05"
            ),
        )
        pause()

        assert calc.ekf is not None

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [1.14, 0.92], ["90", "135"], timestamp="2010-01-01 12:00:10"
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            '{"volume_change": "1.5", "event": "add_media", "source_of_event": "test"}',
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [1.15, 0.93], ["90", "135"], timestamp="2010-01-01 12:00:15"
            ),
        )

        pause()

        assert calc.state_ is not None
        calc.set_state(calc.DISCONNECTED)

    def test_restart(self):

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1, 2: 1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1, 2: 1})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2", "3"],
                [1.15, 0.93, 1.0],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:15",
            ),
            retain=True,
        )

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = '{"1": 1.15, "2": 0.93, "3": 1.0}'

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = '{"1": 1, "2": 1, "3": 1}'

        pause()
        calc1 = GrowthRateCalculator(unit=unit, experiment=experiment)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2", "3"],
                [1.151, 0.931, 1.1],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:20",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2", "3"],
                [1.152, 0.932, 1.2],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:25",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2", "3"],
                [1.153, 0.933, 1.3],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:30",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2", "3"],
                [1.154, 0.934, 1.4],
                ["90", "135", "90"],
                timestamp="2010-01-01 12:00:35",
            ),
        )
        pause()

        assert calc1.state_[-1] != 0
        calc1.set_state(calc1.DISCONNECTED)

        calc2 = GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()
        assert calc2.initial_growth_rate != 0

        calc2.set_state(calc2.DISCONNECTED)

    def test_single_observation(self):

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1"], [1.153], ["90"], timestamp="2010-01-01 12:00:30"
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1"], [1.155], ["90"], timestamp="2010-01-01 12:00:35"
            ),
        )
        pause()

        assert True
        calc.set_state(calc.DISCONNECTED)

    def test_scaling_works(self):

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01 12:00:35"
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        pause()
        assert calc.od_normalization_factors == {"2": 0.8, "1": 0.5}

        calc.set_state(calc.DISCONNECTED)

    def test_shock_from_dosing_works(self):

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 8.2e-07, "2": 8.2e-07})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"],
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
                ["1", "2"],
                [0.51, 0.82],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:00:40",
            ),
        )
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"],
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
                ["1", "2"],
                [0.49, 0.80],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:00:50",
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"],
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
                ["1", "2"],
                [0.40, 0.70],
                ["90,90", "135,45"],
                timestamp="2010-01-01 12:02:00",
            ),
        )
        pause()

        time.sleep(8)
        assert calc.ekf._currently_scaling_covariance
        assert not np.array_equal(previous_covariance_matrix, calc.ekf.covariance_)

        time.sleep(10)
        pause()
        # should revert back
        assert not calc.ekf._currently_scaling_covariance
        assert_array_equal(calc.ekf.covariance_, previous_covariance_matrix)
        calc.set_state(calc.DISCONNECTED)

    def test_end_to_end(self):

        exp = "experiment"
        unit = "unit"
        interval = 0.1
        config["od_config.od_sampling"]["samples_per_second"] = "0.2"

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
        calc.set_state(calc.DISCONNECTED)

    def test_od_blank_being_non_zero(self):

        with local_persistant_storage("od_blank") as cache:
            cache[experiment] = json.dumps({"1": 0.25, "2": 0.4})

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        pause()
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [0.50, 0.80], ["90", "135"], timestamp="2010-01-01 12:02:00"
            ),
            retain=True,
        )

        pause()
        pause()

        assert calc.od_normalization_factors == {"2": 0.8, "1": 0.5}
        assert calc.od_blank == {"2": 0.4, "1": 0.25}
        results = calc.scale_raw_observations({"2": 1.0, "1": 0.6})
        assert abs(results["2"] - 1.5) < 0.00001
        assert abs(results["1"] - 1.4) < 0.00001
        calc.set_state(calc.DISCONNECTED)

    def test_od_blank_being_higher_than_observations(self):

        with local_persistant_storage("od_blank") as cache:
            cache[experiment] = json.dumps({"1": 0.25, "2": 0.4})

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()

        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [0.50, 0.80], ["90", "135"], timestamp="2010-01-01 12:02:00"
            ),
            retain=True,
        )
        pause()
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [0.1, 0.1], ["90", "135"], timestamp="2010-01-01 12:02:05"
            ),
            retain=True,
        )
        pause()
        pause()
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [0.1, 0.1], ["90", "135"], timestamp="2010-01-01 12:02:10"
            ),
            retain=True,
        )
        pause()
        pause()
        calc.set_state(calc.DISCONNECTED)

    def test_od_blank_being_empty(self):

        with local_persistant_storage("od_blank") as cache:
            if experiment in cache:
                del cache[experiment]

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01 12:02:10"
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()

        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01 12:02:15"
            ),
            retain=True,
        )
        pause()
        pause()
        assert calc.od_normalization_factors == {"2": 0.8, "1": 0.5}
        assert calc.od_blank == {"2": 0.0, "1": 0.0}
        results = calc.scale_raw_observations({"2": 1.0, "1": 0.6})
        assert abs(results["2"] - 1.25) < 0.00001
        assert abs(results["1"] - 1.2) < 0.00001
        calc.set_state(calc.DISCONNECTED)

    def test_observation_order_is_preserved_in_job(self):

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 2, "2": 1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1, "2": 1})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["2", "1"], [0.9, 1.1], ["135", "90"], timestamp="2010-01-01 12:00:00"
            ),
            retain=True,
        )
        publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 1.0, "timestamp": "2010-01-01 12:00:00"}),
            retain=True,
        )
        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        assert calc.scale_raw_observations({"2": 2, "1": 0.5}) == {"2": 2.0, "1": 0.25}
        calc.set_state(calc.DISCONNECTED)
