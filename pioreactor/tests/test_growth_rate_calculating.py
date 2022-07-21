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
from pioreactor.utils import local_persistant_storage
from pioreactor.whoami import get_unit_name


def pause() -> None:
    # to avoid race conditions when updating state
    time.sleep(0.5)


def create_od_raw_batched_json(channels=None, voltages=None, angles=None, timestamp=None) -> bytes:
    """
    channel is a list, elements from {1, 2}
    raw_signal is a list
    angle is a list, elements from {45, 90, 135, 180}

    """
    readings = structs.ODReadings(timestamp=timestamp, od_raw=dict())
    for channel, voltage, angle in zip(channels, voltages, angles):
        assert int(channel) in [1, 2]
        readings.od_raw[channel] = structs.ODReading(
            voltage=voltage, angle=angle, timestamp=timestamp, channel=channel
        )

    return encode(readings)


class TestGrowthRateCalculating:
    @classmethod
    def setup_class(cls) -> None:
        # clear the caches and MQTT
        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = None

        with local_persistant_storage("od_blank") as cache:
            for experiment in list(cache.keys()):
                del cache[experiment]

        with local_persistant_storage("od_normalization_mean") as cache:
            for experiment in list(cache.keys()):
                del cache[experiment]

        with local_persistant_storage("od_normalization_variance") as cache:
            for experiment in list(cache.keys()):
                del cache[experiment]

        with local_persistant_storage("growth_rate") as cache:
            for experiment in list(cache.keys()):
                del cache[experiment]

        with local_persistant_storage("od_filtered") as cache:
            for experiment in list(cache.keys()):
                del cache[experiment]

    def test_subscribing(self) -> None:

        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "90"

        unit = get_unit_name()
        experiment = "test_subscribing"

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1})

        with local_persistant_storage("growth_rate") as cache:
            cache[experiment] = str(1.0)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["2", "1"], [0.9, 1.1], ["135", "90"], timestamp="2010-01-01 12:00:00"
            ),
            retain=True,
        )

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            pause()
            assert calc.initial_growth_rate == 1.0

            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                create_od_raw_batched_json(
                    ["1", "2"],
                    [1.12, 0.88],
                    ["90", "135"],
                    timestamp="2010-01-01 12:00:05",
                ),
            )
            pause()
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                create_od_raw_batched_json(
                    ["2", "1"],
                    [0.87, 1.14],
                    ["135", "90"],
                    timestamp="2010-01-01 12:00:05",
                ),
            )
            pause()
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                create_od_raw_batched_json(
                    ["2", "1"],
                    [0.85, 1.16],
                    ["135", "90"],
                    timestamp="2010-01-01 12:00:05",
                ),
            )
            pause()

            assert calc.ekf is not None

            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                create_od_raw_batched_json(
                    ["1", "2"],
                    [1.14, 0.92],
                    ["90", "135"],
                    timestamp="2010-01-01 12:00:10",
                ),
            )
            publish(
                f"pioreactor/{unit}/{experiment}/dosing_events",
                encode(
                    structs.DosingEvent(
                        volume_change=1.5,
                        event="add_media",
                        source_of_event="test",
                        timestamp="2010-01-01 12:00:12",
                    )
                ),
            )
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                create_od_raw_batched_json(
                    ["1", "2"],
                    [1.15, 0.93],
                    ["90", "135"],
                    timestamp="2010-01-01 12:00:15",
                ),
            )

            pause()

            assert calc.ekf.state_ is not None

    def test_restart(self) -> None:
        unit = get_unit_name()
        experiment = "test_restart"

        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "135"

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1, 2: 1})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"],
                [
                    1.15,
                    0.93,
                ],
                ["90", "135"],
                timestamp="2010-01-01 12:00:15",
            ),
            retain=True,
        )

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = '{"1": 1.15, "2": 0.93}'

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = '{"1": 1, "2": 1}'

        pause()
        calc1 = GrowthRateCalculator(unit=unit, experiment=experiment)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"],
                [1.151, 0.931],
                ["90", "135"],
                timestamp="2010-01-01 12:00:20",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"],
                [1.152, 0.932],
                ["90", "135"],
                timestamp="2010-01-01 12:00:25",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"],
                [1.153, 0.933],
                ["90", "135"],
                timestamp="2010-01-01 12:00:30",
            ),
        )
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1", "2"],
                [1.154, 0.934],
                ["90", "135"],
                timestamp="2010-01-01 12:00:35",
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

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(["1"], [1.153], ["90"], timestamp="2010-01-01 12:00:30"),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(["1"], [1.155], ["90"], timestamp="2010-01-01 12:00:35"),
        )
        pause()

        assert True
        calc.clean_up()

    def test_scaling_works(self) -> None:
        unit = get_unit_name()
        experiment = "test_scaling_works"

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

        calc.clean_up()

    def test_shock_from_dosing_works(self) -> None:
        unit = get_unit_name()
        experiment = "test_shock_from_dosing_works"

        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "REF"

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 8.2e-07})

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1"],
                [0.5],
                ["90"],
                timestamp="2010-01-01 12:00:35",
            ),
            retain=True,
        )

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1"],
                [0.51],
                ["90"],
                timestamp="2010-01-01 12:00:40",
            ),
        )
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1"],
                [0.51],
                ["90"],
                timestamp="2010-01-01 12:00:45",
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
                    timestamp="2010-01-01 12:00:48",
                )
            ),
        )
        pause()

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1"],
                [0.49],
                ["90"],
                timestamp="2010-01-01 12:00:50",
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1"],
                [0.48],
                ["90"],
                timestamp="2010-01-01 12:00:55",
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
                    timestamp="2010-01-01 12:01:55",
                )
            ),
        )
        pause()
        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["1"],
                [0.40],
                ["90"],
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
        while calc.ekf._currently_scaling_covariance:
            pass

        assert_array_equal(calc.ekf.covariance_, previous_covariance_matrix)
        calc.clean_up()

    def test_end_to_end(self) -> None:

        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = "135"

        unit = get_unit_name()
        experiment = "test_end_to_end"

        interval = 0.1
        config["od_config"]["samples_per_second"] = "0.2"

        od = start_od_reading(
            "135",
            "90",
            interval=interval,
            unit=unit,
            experiment=experiment,
            fake_data=True,
        )

        st = start_stirring(target_rpm=500, unit=unit, experiment=experiment)

        calc = GrowthRateCalculator(unit=unit, experiment=experiment)

        time.sleep(35)
        assert calc.ekf.state_[-2] != 1.0
        calc.clean_up()
        st.clean_up()
        od.clean_up()

    def test_180_angle(self) -> None:
        import json
        import numpy as np
        from pioreactor.utils.timing import RepeatedTimer

        unit = get_unit_name()
        experiment = "test_180_angle"
        samples_per_second = 0.2
        config["od_config"]["samples_per_second"] = str(samples_per_second)
        config["od_config.photodiode_channel"]["1"] = "180"
        config["od_config.photodiode_channel"]["2"] = None

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 3.3})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 8.2e-02})

        class Mock180ODReadings:

            growth_rate = 0.1
            od_reading = 1.0

            def __call__(self):
                self.od_reading *= np.exp(self.growth_rate / 60 / 60 / samples_per_second)

                voltage = 3.3 * np.exp(-(self.od_reading - 1))
                payload = {
                    "od_raw": {
                        "1": {
                            "voltage": voltage,
                            "angle": "180",
                            "timestamp": "2021-06-06T15:08:12.081153",
                            "channel": "1",
                        }
                    },
                    "timestamp": "2021-06-06T15:08:12.081153",
                }

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
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
        config["od_config"]["samples_per_second"] = str(samples_per_second)
        config["od_config.photodiode_channel"]["1"] = "90"
        config["od_config.photodiode_channel"]["2"] = None

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 8.2e-02})

        class Mock180ODReadings:

            growth_rate = 0.1
            od_reading = 1.0

            def __call__(self):
                self.od_reading *= np.exp(self.growth_rate / 60 / 60 / samples_per_second)

                voltage = 0.1 * self.od_reading
                payload = {
                    "od_raw": {
                        "1": {
                            "voltage": voltage,
                            "angle": "90",
                            "timestamp": "2021-06-06T15:08:12.081153",
                            "channel": "1",
                        }
                    },
                    "timestamp": "2021-06-06T15:08:12.081153",
                }

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
                    json.dumps(payload),
                )

        thread = RepeatedTimer(0.025, Mock180ODReadings()).start()

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            time.sleep(35)

            assert calc.ekf.state_[1] > 0

        thread.cancel()

    def test_od_blank_being_non_zero(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_non_zero"
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
        print(results)
        assert abs(results["2"] - 1.5) < 0.00001
        assert abs(results["1"] - 1.4) < 0.00001
        calc.clean_up()

    def test_od_blank_being_higher_than_observations(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_higher_than_observations"
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
        calc.clean_up()

    def test_od_blank_being_empty(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_empty"
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

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
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

    def test_observation_order_is_preserved_in_job(self) -> None:
        unit = get_unit_name()
        experiment = "test_observation_order_is_preserved_in_job"
        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 2, "2": 1})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1, "2": 1})

        with local_persistant_storage("growth_rate") as cache:
            cache[experiment] = str(1.0)

        publish(
            f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
            create_od_raw_batched_json(
                ["2", "1"], [0.9, 1.1], ["135", "90"], timestamp="2010-01-01 12:00:00"
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
        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 0})

        with local_persistant_storage("od_blank") as cache:
            cache[experiment] = json.dumps({"1": 0})

        with collect_all_logs_of_level("ERROR", unit, experiment) as bucket:
            with GrowthRateCalculator(unit=unit, experiment=experiment):
                assert len(bucket) > 0

    def test_ability_to_yield_into_growth_rate_calc(self) -> None:
        unit = "unit"
        experiment = "test_ability_to_yield_into_growth_rate_calc"

        with local_persistant_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1.0})

        with local_persistant_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1.0})

        od_stream = start_od_reading(
            "90",
            "REF",
            interval=1.0,
            fake_data=True,
            unit=unit,
            experiment=experiment,
        )
        gr = GrowthRateCalculator(unit=unit, experiment=experiment, from_mqtt=False)
        results = []

        for i, reading in enumerate(od_stream):
            results.append(gr.update_state_from_observation(reading))
            if i == 5:
                break

        assert len(results) > 0
        assert results[0][0].timestamp < results[1][0].timestamp < results[2][0].timestamp  # type: ignore
        od_stream.clean_up()
