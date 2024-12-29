# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time

import numpy as np
from msgspec.json import encode
from numpy.testing import assert_array_equal

from pioreactor import structs
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring
from pioreactor.config import config
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import default_datetime_for_pioreactor
from pioreactor.utils.timing import to_datetime
from pioreactor.whoami import get_unit_name


def pause() -> None:
    # to avoid race conditions when updating state
    time.sleep(0.5)


def create_od_raw_batched_json(channels, voltages: list[float], angles, timestamp: str) -> bytes:
    """
    channel is a list, elements from {1, 2}
    raw_signal is a list
    angle is a list, elements from {45, 90, 135, 180}

    """
    readings = structs.ODReadings(timestamp=to_datetime(timestamp), ods=dict())
    for channel, voltage, angle in zip(channels, voltages, angles):
        assert int(channel) in (1, 2)
        readings.ods[channel] = structs.ODReading(
            od=voltage, angle=angle, timestamp=to_datetime(timestamp), channel=channel
        )

    return encode(readings)


class TestGrowthRateCalculating:
    @classmethod
    def setup_class(cls) -> None:
        # clear the caches and MQTT
        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = None  # type: ignore

        with local_persistent_storage("od_blank") as cache:
            for experiment in cache.iterkeys():
                del cache[experiment]

        with local_persistent_storage("od_normalization_mean") as cache:
            for experiment in cache.iterkeys():
                del cache[experiment]

        with local_persistent_storage("od_normalization_variance") as cache:
            for experiment in cache.iterkeys():
                del cache[experiment]

        with local_persistent_storage("growth_rate") as cache:
            for experiment in cache.iterkeys():
                del cache[experiment]

        with local_persistent_storage("od_filtered") as cache:
            for experiment in cache.iterkeys():
                del cache[experiment]

    def test_subscribing(self) -> None:
        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "90"

        unit = get_unit_name()
        experiment = "test_subscribing"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1.0, 2: 1.0})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1e-3, 2: 1e-3})

        with local_persistent_storage("growth_rate") as cache:
            cache[experiment] = 1.0

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"], [1.01, 0.99], ["90", "135"], timestamp="2010-01-01T12:00:00.000000Z"
            ),
            retain=True,
        )

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            pause()
            assert calc.initial_growth_rate == 1.0

            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(
                    ["1", "2"],
                    [1.012, 0.985],
                    ["90", "135"],
                    timestamp="2010-01-01T12:00:15.000000Z",
                ),
            )
            pause()
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(
                    ["1", "2"],
                    [1.014, 0.987],
                    ["90", "135"],
                    timestamp="2010-01-01T12:00:15.000000Z",
                ),
            )
            pause()
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(
                    ["1", "2"],
                    [1.016, 0.985],
                    ["90", "135"],
                    timestamp="2010-01-01T12:00:15.000000Z",
                ),
            )
            pause()

            assert calc.ekf is not None

            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(
                    ["1", "2"],
                    [1.014, 0.992],
                    ["90", "135"],
                    timestamp="2010-01-01T12:00:15.000000Z",
                ),
            )
            publish(
                f"pioreactor/{unit}/{experiment}/dosing_events",
                encode(
                    structs.DosingEvent(
                        volume_change=1.5,
                        event="add_media",
                        source_of_event="test",
                        timestamp=default_datetime_for_pioreactor(4),
                    )
                ),
            )
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(
                    ["1", "2"],
                    [1.015, 0.993],
                    ["90", "135"],
                    timestamp="2010-01-01T12:00:15.000000Z",
                ),
            )

            pause()

            assert calc.ekf.state_ is not None

    def test_restart(self) -> None:
        unit = get_unit_name()
        experiment = "test_restart"

        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "135"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"],
                [
                    1.15,
                    0.93,
                ],
                ["90", "135"],
                timestamp="2010-01-01T12:00:15.000000Z",
            ),
            retain=True,
        )

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = '{"1": 1.15, "2": 0.93}'

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = '{"1": 1, "2": 1}'

        pause()
        calc1 = GrowthRateCalculator(unit=unit, experiment=experiment)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"],
                [1.151, 0.931],
                ["90", "135"],
                timestamp="2010-01-01T12:00:20.000000Z",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"],
                [1.152, 0.932],
                ["90", "135"],
                timestamp="2010-01-01T12:00:25.000000Z",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"],
                [1.153, 0.933],
                ["90", "135"],
                timestamp="2010-01-01T12:00:30.000000Z",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"],
                [1.154, 0.934],
                ["90", "135"],
                timestamp="2010-01-01T12:00:35.000000Z",
            ),
        )
        pause()

        assert calc1.ekf.state_[-1] != 0
        calc1.clean_up()

        calc2 = GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()
        assert calc2.initial_growth_rate != 0

        calc2.clean_up()

    def test_single_observation(self) -> None:
        unit = get_unit_name()
        experiment = "test_single_observation"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(["1"], [1.153], ["90"], timestamp="2010-01-01T12:00:30.000000Z"),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(["1"], [1.155], ["90"], timestamp="2010-01-01T12:00:35.000000Z"),
        )
        pause()

        assert True
        calc.clean_up()

    def test_scaling_works(self) -> None:
        unit = get_unit_name()
        experiment = "test_scaling_works"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01T12:00:35.000000Z"
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        pause()
        assert calc.od_normalization_factors == {"2": 0.8, "1": 0.5}

        calc.clean_up()

    def test_shock_from_dosing_works(self) -> None:
        unit = get_unit_name()
        experiment = "test_shock_from_dosing_works"

        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "REF"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 8.2e-07})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1"],
                [0.5],
                ["90"],
                timestamp="2010-01-01T12:00:35.000000Z",
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1"],
                [0.51],
                ["90"],
                timestamp="2010-01-01T12:00:40.000000Z",
            ),
        )
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1"],
                [0.51],
                ["90"],
                timestamp="2010-01-01T12:00:45.000000Z",
            ),
        )
        pause()

        previous_covariance_matrix = calc.ekf.covariance_.copy()

        # trigger dosing events, which change the "regime"
        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            encode(
                structs.DosingEvent(
                    volume_change=1.0,
                    event="add_media",
                    source_of_event="algo",
                    timestamp=to_datetime("2010-01-01T12:00:48.000000Z"),
                )
            ),
        )
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1"],
                [0.49],
                ["90"],
                timestamp="2010-01-01T12:00:50.000000Z",
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1"],
                [0.48],
                ["90"],
                timestamp="2010-01-01T12:00:55.000000Z",
            ),
        )
        pause()

        assert not np.array_equal(previous_covariance_matrix, calc.ekf.covariance_)

        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            encode(
                structs.DosingEvent(
                    volume_change=1.0,
                    event="add_media",
                    source_of_event="algo",
                    timestamp=to_datetime("2010-01-01T12:01:55.000000Z"),
                )
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1"],
                [0.40],
                ["90"],
                timestamp="2010-01-01T12:02:00.000000Z",
            ),
        )
        pause()

        time.sleep(8)
        assert calc.ekf._currently_scaling_covariance
        assert not np.array_equal(previous_covariance_matrix, calc.ekf.covariance_)

        time.sleep(10)
        pause()

        # should revert back
        while calc.ekf._currently_scaling_covariance:
            pass

        assert_array_equal(calc.ekf.covariance_, previous_covariance_matrix)
        calc.clean_up()

    def test_end_to_end(self) -> None:
        config["od_config.photodiode_channel"]["1"] = "REF"
        config["od_config.photodiode_channel"]["2"] = "90"

        unit = get_unit_name()
        experiment = "test_end_to_end"

        interval = 0.1
        config["od_reading.config"]["samples_per_second"] = "0.2"

        with start_od_reading(
            "REF",
            "90",
            interval=interval,
            unit=unit,
            experiment=experiment,
            fake_data=True,
        ), start_stirring(target_rpm=500, unit=unit, experiment=experiment), GrowthRateCalculator(
            unit=unit, experiment=experiment
        ) as calc:
            time.sleep(25)
            assert calc.ekf.state_[-2] != 1.0

    def test_180_angle(self) -> None:
        import json
        import numpy as np
        from pioreactor.utils.timing import RepeatedTimer

        unit = get_unit_name()
        experiment = "test_180_angle"
        samples_per_second = 0.2
        config["od_reading.config"]["samples_per_second"] = str(samples_per_second)
        config["od_config.photodiode_channel"]["1"] = "180"
        config["od_config.photodiode_channel"]["2"] = None  # type: ignore

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 3.3})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6})

        class Mock180ODReadings:
            growth_rate = 0.05
            od_reading = 1.0

            def __call__(self):
                self.od_reading *= np.exp(self.growth_rate / 60 / 60 / samples_per_second)

                voltage = 3.3 * np.exp(-(self.od_reading - 1))
                payload = {
                    "ods": {
                        "1": {
                            "od": voltage,
                            "angle": "180",
                            "timestamp": "2021-06-06T15:08:12.081153Z",
                            "channel": "1",
                        }
                    },
                    "timestamp": "2021-06-06T15:08:12.081153Z",
                }

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    json.dumps(payload),
                )

        thread = RepeatedTimer(0.025, Mock180ODReadings()).start()

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            time.sleep(35)

            assert calc.ekf.state_[1] > 0
            thread.cancel()

    def test_90_angle(self) -> None:
        import json
        import numpy as np
        from pioreactor.utils.timing import RepeatedTimer

        unit = get_unit_name()
        experiment = "test_90_angle"
        samples_per_second = 0.2
        config["od_reading.config"]["samples_per_second"] = str(samples_per_second)
        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = None  # type: ignore

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.1})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6})

        class Mock90ODReadings:
            growth_rate = 0.025
            od_reading = 1.0

            def __call__(self):
                self.od_reading *= np.exp(self.growth_rate / 60 / 60 / samples_per_second)

                voltage = 0.1 * self.od_reading
                payload = {
                    "ods": {
                        "1": {
                            "od": voltage,
                            "angle": "90",
                            "timestamp": "2021-06-06T15:08:12.081153Z",
                            "channel": "1",
                        }
                    },
                    "timestamp": "2021-06-06T15:08:12.081153Z",
                }
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    json.dumps(payload),
                )

        thread = RepeatedTimer(0.025, Mock90ODReadings()).start()

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            time.sleep(35)

            assert calc.ekf.state_[1] > 0

        thread.cancel()

    def test_od_blank_being_non_zero(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_non_zero"

        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "135"

        with local_persistent_storage("od_blank") as cache:
            cache[experiment] = json.dumps({"1": 0.25, "2": 0.4})

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        pause()
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"], [0.50, 0.80], ["90", "135"], timestamp="2010-01-01T12:02:00.000000Z"
            ),
            retain=True,
        )

        pause()
        pause()

        assert calc.od_normalization_factors == {"2": 0.8, "1": 0.5}
        assert calc.od_blank == {"2": 0.4, "1": 0.25}
        results = calc.scale_raw_observations({"2": 1.0, "1": 0.6})
        assert results is not None
        assert abs(results["2"] - 1.5) < 0.00001
        assert abs(results["1"] - 1.4) < 0.00001
        calc.clean_up()

    def test_od_blank_being_higher_than_observations(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_higher_than_observations"
        with local_persistent_storage("od_blank") as cache:
            cache[experiment] = json.dumps({"1": 0.25, "2": 0.4})

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)
        pause()

        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"], [0.50, 0.80], ["90", "135"], timestamp="2010-01-01T12:02:00.000000Z"
            ),
            retain=True,
        )
        pause()
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"], [0.1, 0.1], ["90", "135"], timestamp="2010-01-01T12:02:05.000000Z"
            ),
            retain=True,
        )
        pause()
        pause()
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"], [0.1, 0.1], ["90", "135"], timestamp="2010-01-01T12:02:10.000000Z"
            ),
            retain=True,
        )
        pause()
        pause()
        calc.clean_up()

    def test_od_blank_being_empty(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_empty"

        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "135"

        with local_persistent_storage("od_blank") as cache:
            if experiment in cache:
                del cache[experiment]

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01T12:02:10.000000Z"
            ),
            retain=True,
        )

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            pause()

            pause()
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(
                    ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01T12:02:15.000000Z"
                ),
                retain=True,
            )
            pause()
            pause()
            assert calc.od_normalization_factors == {"2": 0.8, "1": 0.5}
            assert calc.od_blank == {"2": 0.0, "1": 0.0}
            results = calc.scale_raw_observations({"2": 1.0, "1": 0.6})
            assert results is not None
            assert abs(results["2"] - 1.25) < 0.00001
            assert abs(results["1"] - 1.2) < 0.00001

    def test_observation_order_is_preserved_in_job(self) -> None:
        unit = get_unit_name()
        experiment = "test_observation_order_is_preserved_in_job"
        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 2, "2": 1})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1, "2": 1})

        with local_persistent_storage("growth_rate") as cache:
            cache[experiment] = str(1.0)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["2", "1"], [0.9, 1.1], ["135", "90"], timestamp="2010-01-01T12:00:00.000000Z"
            ),
            retain=True,
        )

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            assert calc.scale_raw_observations({"2": 2, "1": 0.5}) == {
                "2": 2.0,
                "1": 0.25,
            }

    def test_zero_blank_and_zero_od_coming_in(self) -> None:
        unit = get_unit_name()
        experiment = "test_zero_blank_and_zero_od_coming_in"
        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 0})

        with local_persistent_storage("od_blank") as cache:
            cache[experiment] = json.dumps({"1": 0})

        with collect_all_logs_of_level("ERROR", unit, experiment) as bucket:
            with GrowthRateCalculator(unit=unit, experiment=experiment):
                pause()
                pause()
                assert len(bucket) > 0

    def test_ability_to_yield_into_growth_rate_calc(self) -> None:
        unit = "unit"
        experiment = "test_ability_to_yield_into_growth_rate_calc"

        config["od_config.photodiode_channel"]["1"] = "REF"
        config["od_config.photodiode_channel"]["2"] = "90"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({2: 0.05})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({2: 1e-5})

        with start_od_reading(
            "REF",
            "90",
            interval=1.0,
            fake_data=True,
            unit=unit,
            experiment=experiment,
            use_calibration=False,
        ) as od_stream:
            with GrowthRateCalculator(unit=unit, experiment=experiment, source_obs_from_mqtt=False) as gr:
                results = []

                for i, reading in enumerate(od_stream):
                    results.append(gr.update_state_from_observation(reading))
                    if i == 5:
                        break

                assert len(results) > 0
                assert results[0][0].timestamp < results[1][0].timestamp < results[2][0].timestamp  # type: ignore

    def test_a_non_unity_initial_nOD_works(self) -> None:
        unit = get_unit_name()
        experiment = "test_a_non_unity_initial_nOD_works"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.05, "2": 0.10})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-6})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            create_od_raw_batched_json(
                ["1", "2"], [1.0, 1.0], ["90", "135"], timestamp="2010-01-01T12:00:35.000000Z"
            ),
            retain=True,
        )

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            pause()
            assert calc.od_normalization_factors == {"1": 0.05, "2": 0.10}
            assert calc.initial_nOD == 15.0 == 0.5 * (1 / 0.05 + 1 / 0.10)

    def test_single_outlier_spike_gets_absorbed(self) -> None:
        config["od_config.photodiode_channel"]["1"] = "REF"
        config["od_config.photodiode_channel"]["2"] = "90"

        unit = get_unit_name()
        experiment = "test_single_outlier_spike_gets_absorbed"

        config["od_reading.config"]["samples_per_second"] = "0.2"

        # clear mqtt
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            None,
            retain=True,
        )
        var = 1e-6
        std = float(np.sqrt(var))
        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"2": 0.05})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"2": var})

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            for _ in range(30):
                v = 0.05 + std * np.random.randn()
                t = current_utc_timestamp()
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                    retain=True,
                )
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od2",
                    encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                    retain=True,
                )
                time.sleep(0.5)

            previous_nOD = calc.od_filtered
            previous_gr = calc.growth_rate
            # EKF is warmed up, introduce outlier. This outlier is "expected", given the smoothing we do.
            v = 0.10 + std * np.random.randn()
            t = current_utc_timestamp()
            calc.publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                retain=True,
            )
            calc.publish(
                f"pioreactor/{unit}/{experiment}/od_reading/od2",
                encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                retain=True,
            )

            v = 0.06 + std * np.random.randn()
            t = current_utc_timestamp()
            calc.publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                retain=True,
            )
            calc.publish(
                f"pioreactor/{unit}/{experiment}/od_reading/od2",
                encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                retain=True,
            )
            time.sleep(0.5)

            current_nOD = calc.od_filtered
            current_gr = calc.growth_rate

            assert previous_nOD.od_filtered < current_nOD.od_filtered
            assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

            # continue normal data
            for _ in range(30):
                v = 0.05 + std * np.random.randn()
                t = current_utc_timestamp()
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                    retain=True,
                )
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od2",
                    encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                    retain=True,
                )
                time.sleep(0.5)

            # reverts back to previous
            current_nOD = calc.od_filtered
            current_gr = calc.growth_rate

            assert abs(previous_nOD.od_filtered - current_nOD.od_filtered) < 0.05
            assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

    def test_baseline_shift_gets_absorbed(self) -> None:
        config["od_config.photodiode_channel"]["1"] = "REF"
        config["od_config.photodiode_channel"]["2"] = "90"

        unit = get_unit_name()
        experiment = "test_baseline_shift_gets_absorbed"

        config["od_reading.config"]["samples_per_second"] = "0.2"

        # clear mqtt
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            None,
            retain=True,
        )

        var = 1e-6
        std = float(np.sqrt(var))
        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"2": 0.05})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"2": std**2})

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            for _ in range(30):
                v = 0.05 + std * np.random.randn()
                t = current_utc_timestamp()
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                    retain=True,
                )
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od2",
                    encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                    retain=True,
                )
                time.sleep(0.5)

            previous_gr = calc.growth_rate
            # EKF is warmed up,

            # offset
            calc.logger.info("OFFSET!")
            for _ in range(30):
                v = 0.05 + 0.01 + std * np.random.randn()
                t = current_utc_timestamp()
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                    retain=True,
                )
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od2",
                    encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                    retain=True,
                )
                time.sleep(0.5)

            # reverts back to previous
            current_gr = calc.growth_rate

            assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

    def test_massive_outlier_spike_gets_absorbed(self) -> None:
        config["od_config.photodiode_channel"]["1"] = "REF"
        config["od_config.photodiode_channel"]["2"] = "90"

        unit = get_unit_name()
        experiment = "test_massive_outlier_spike_gets_absorbed"

        config["od_reading.config"]["samples_per_second"] = "0.2"

        # clear mqtt
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            None,
            retain=True,
        )
        var = 1e-6
        std = float(np.sqrt(var))
        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"2": 0.05})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"2": var})

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            for _ in range(30):
                v = 0.05 + std * np.random.randn()
                t = current_utc_timestamp()
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                    retain=True,
                )
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od2",
                    encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                    retain=True,
                )
                time.sleep(0.5)

            previous_nOD = calc.od_filtered
            previous_gr = calc.growth_rate

            v = 0.6 + std * np.random.randn()
            t = current_utc_timestamp()
            calc.publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                retain=True,
            )
            calc.publish(
                f"pioreactor/{unit}/{experiment}/od_reading/od2",
                encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                retain=True,
            )
            time.sleep(0.5)

            current_nOD = calc.od_filtered
            current_gr = calc.growth_rate

            assert previous_nOD.od_filtered < current_nOD.od_filtered
            assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

            # continue normal data
            for _ in range(30):
                v = 0.05 + std * np.random.randn()
                t = current_utc_timestamp()
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_od_raw_batched_json(["2"], [v], ["90"], timestamp=t),
                    retain=True,
                )
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od2",
                    encode(structs.ODReading(od=v, angle="90", timestamp=to_datetime(t), channel="2")),
                    retain=True,
                )
                time.sleep(0.5)

            # reverts back to previous
            current_nOD = calc.od_filtered
            current_gr = calc.growth_rate

            assert abs(previous_nOD.od_filtered - current_nOD.od_filtered) < 0.05
            assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01
