# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time

import numpy as np
import pytest
from msgspec.json import encode
from pioreactor import structs
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.config import config
from pioreactor.config import temporary_config_changes
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import create_client
from pioreactor.pubsub import publish
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.streaming import EmptyDosingSource
from pioreactor.utils.streaming import ExportDosingSource
from pioreactor.utils.streaming import ExportODSource
from pioreactor.utils.streaming import MqttDosingSource
from pioreactor.utils.streaming import MqttODSource
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import default_datetime_for_pioreactor
from pioreactor.utils.timing import to_datetime
from pioreactor.whoami import get_unit_name

from .utils import wait_for


def pause() -> None:
    # to avoid race conditions when updating state
    time.sleep(0.5)


def create_od_raw_batched(channels, voltages: list[float], angles, timestamp: str) -> structs.ODReadings:
    """
    channel is a list, elements from {1, 2}
    raw_signal is a list
    angle is a list, elements from {45, 90, 135, 180}

    """
    readings = structs.ODReadings(timestamp=to_datetime(timestamp), ods=dict())
    for channel, voltage, angle in zip(channels, voltages, angles):
        assert int(channel) in (1, 2)
        readings.ods[channel] = structs.RawODReading(
            od=voltage, angle=angle, timestamp=to_datetime(timestamp), channel=channel, ir_led_intensity=80
        )

    return readings


def create_encoded_od_raw_batched(channels, voltages: list[float], angles, timestamp: str) -> bytes:
    """
    channel is a list, elements from {1, 2}
    raw_signal is a list
    angle is a list, elements from {45, 90, 135, 180}

    """
    return encode(create_od_raw_batched(channels, voltages, angles, timestamp))


def create_od_stream_from_mqtt(unit, experiment):
    """
    Create a stream of OD readings from the MQTT topic for a given experiment.
    """
    return MqttODSource(unit, experiment, skip_first=0)


def create_dosing_stream_from_mqtt(unit, experiment):
    """
    Create a stream of OD readings from the MQTT topic for a given experiment.
    """
    return MqttDosingSource(unit, experiment)


class TestGrowthRateCalculating:
    @classmethod
    def setup_class(cls) -> None:
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
        with temporary_config_changes(
            config, [("od_config.photodiode_channel", "1", "90"), ("od_config.photodiode_channel", "2", "90")]
        ):
            unit = get_unit_name()
            experiment = "test_subscribing"

            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({1: 1.0, 2: 1.0})

            with local_persistent_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps({1: 1e-3, 2: 1e-3})

            with local_persistent_storage("growth_rate") as cache:
                cache[experiment] = 1.0

            od_stream, dosing_stream = create_od_stream_from_mqtt(
                unit, experiment
            ), create_dosing_stream_from_mqtt(unit, experiment)
            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.012, 0.985],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:15.000Z",
                    ),
                )
                pause()
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.014, 0.987],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:15.000Z",
                    ),
                )
                pause()
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.016, 0.985],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:15.000Z",
                    ),
                )
                pause()

                assert calc.processor.ekf is not None

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.014, 0.992],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:15.000Z",
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
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.015, 0.993],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:15.000Z",
                    ),
                )

                pause()

                assert calc.processor.ekf.state_ is not None

    @pytest.mark.flakey
    def test_restart(self) -> None:
        unit = get_unit_name()
        experiment = "test_restart"

        with temporary_config_changes(
            config, [("od_config.photodiode_channel", "1", "90"), ("od_config.photodiode_channel", "2", "90")]
        ):
            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"1": 1.15, "2": 0.93})

            with local_persistent_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps({"1": 1, "2": 1})

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc1:
                od_stream, dosing_stream = create_od_stream_from_mqtt(
                    unit, experiment
                ), create_dosing_stream_from_mqtt(unit, experiment)
                calc1.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.151, 0.931],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:20.000Z",
                    ),
                )
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.152, 0.932],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:25.000Z",
                    ),
                )
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.153, 0.933],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:30.000Z",
                    ),
                )
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.154, 0.934],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:35.000Z",
                    ),
                )
                assert wait_for(lambda: float(calc1.processor.ekf.state_[-1]) != 0, timeout=3.0)

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc2:
                od_stream, dosing_stream = create_od_stream_from_mqtt(
                    unit, experiment
                ), create_dosing_stream_from_mqtt(unit, experiment)

                calc2.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)
                pause()
                pause()
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.154, 0.934],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:35.000Z",
                    ),
                )
                assert wait_for(lambda: float(calc2.processor.ekf.state_[-1]) != 0, timeout=3.0)

    def test_single_observation(self) -> None:
        unit = get_unit_name()
        experiment = "test_single_observation"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({1: 1})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({1: 1})

        od_stream, dosing_stream = create_od_stream_from_mqtt(
            unit, experiment
        ), create_dosing_stream_from_mqtt(unit, experiment)

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_encoded_od_raw_batched(["1"], [1.155], ["90"], timestamp="2010-01-01T12:00:35.000Z"),
            )
            pause()

    def test_scaling_works(self) -> None:
        unit = get_unit_name()
        experiment = "test_scaling_works"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        od_stream, dosing_stream = create_od_stream_from_mqtt(
            unit, experiment
        ), create_dosing_stream_from_mqtt(unit, experiment)

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_encoded_od_raw_batched(
                    ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01T12:00:35.000Z"
                ),
            )
            pause()
            assert calc.processor.od_normalization_factors == {"2": 0.8, "1": 0.5}

            # job expects one more od reading for initial values, else it WARNs.
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_encoded_od_raw_batched(
                    ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01T12:00:35.000Z"
                ),
            )

    def test_shock_from_dosing_works(self) -> None:
        unit = get_unit_name()
        experiment = "test_shock_from_dosing_works"

        with temporary_config_changes(
            config,
            [("od_config.photodiode_channel", "1", "90"), ("od_config.photodiode_channel", "2", "REF")],
        ):
            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"1": 0.5})

            with local_persistent_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps({"1": 8.2e-07})

            od_stream, dosing_stream = create_od_stream_from_mqtt(
                unit, experiment
            ), create_dosing_stream_from_mqtt(unit, experiment)

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1"],
                        [0.51],
                        ["90"],
                        timestamp="2010-01-01T12:00:40.000Z",
                    ),
                )
                pause()

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1"],
                        [0.51],
                        ["90"],
                        timestamp="2010-01-01T12:00:45.000Z",
                    ),
                )
                pause()

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1"],
                        [0.52],
                        ["90"],
                        timestamp="2010-01-01T12:00:50.000Z",
                    ),
                )
                pause()
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1"],
                        [0.52],
                        ["90"],
                        timestamp="2010-01-01T12:00:55.000Z",
                    ),
                )
                pause()

                publish(
                    f"pioreactor/{unit}/{experiment}/dosing_events",
                    encode(
                        structs.DosingEvent(
                            volume_change=1.0,
                            event="add_media",
                            source_of_event="algo",
                            timestamp=to_datetime("2010-01-01T12:01:55.000Z"),
                        )
                    ),
                )
                pause()
                assert calc.processor._recent_dilution
                pause()
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1"],
                        [0.40],
                        ["90"],
                        timestamp="2010-01-01T12:02:00.000Z",
                    ),
                )
                pause()
                pause()
                assert not calc.processor._recent_dilution

    @pytest.mark.slow
    def test_180_angle(self) -> None:
        import json
        import numpy as np
        from pioreactor.utils.timing import RepeatedTimer

        unit = get_unit_name()
        experiment = "test_180_angle"
        samples_per_second = 0.2

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 3.3})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6})

        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "180"),
                ("od_config.photodiode_channel", "2", None),
                ("od_reading.config", "samples_per_second", str(samples_per_second)),
            ],
        ):
            # config["od_reading.config"]["samples_per_second"] = str(samples_per_second)
            # config["od_config.photodiode_channel"]["1"] = "180"
            # config["od_config.photodiode_channel"]["2"] = None  # type: ignore

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
                                "calibrated": 0,
                                "ir_led_intensity": 80,
                            }
                        },
                        "timestamp": "2021-06-06T15:08:12.081153Z",
                    }

                    publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        json.dumps(payload),
                    )

            thread = RepeatedTimer(0.025, Mock180ODReadings()).start()
            od_stream, dosing_stream = create_od_stream_from_mqtt(
                unit, experiment
            ), create_dosing_stream_from_mqtt(unit, experiment)

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)
                time.sleep(35)

                assert calc.processor.ekf.state_[1] > 0
                thread.cancel()

    @pytest.mark.slow
    def test_90_angle(self) -> None:
        import json
        import numpy as np
        from pioreactor.utils.timing import RepeatedTimer

        unit = get_unit_name()
        experiment = "test_90_angle"
        samples_per_second = 0.2

        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "90"),
                ("od_config.photodiode_channel", "2", None),
                ("od_reading.config", "samples_per_second", str(samples_per_second)),
            ],
        ):
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
                                "calibrated": 0,
                                "ir_led_intensity": 80,
                            }
                        },
                        "timestamp": "2021-06-06T15:08:12.081153Z",
                    }
                    publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        json.dumps(payload),
                    )

            thread = RepeatedTimer(0.025, Mock90ODReadings()).start()
            od_stream, dosing_stream = create_od_stream_from_mqtt(
                unit, experiment
            ), create_dosing_stream_from_mqtt(unit, experiment)

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                time.sleep(35)

                assert calc.processor.ekf.state_[1] > 0

            thread.cancel()

    def test_od_blank_being_non_zero(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_non_zero"

        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "90"),
                ("od_config.photodiode_channel", "2", "135"),
            ],
        ):
            with local_persistent_storage("od_blank") as cache:
                cache[experiment] = json.dumps({"1": 0.25, "2": 0.4})

            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

            with local_persistent_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

            od_stream, dosing_stream = create_od_stream_from_mqtt(
                unit, experiment
            ), create_dosing_stream_from_mqtt(unit, experiment)

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                pause()
                pause()

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"], [0.50, 0.80], ["90", "135"], timestamp="2010-01-01T12:02:00.000Z"
                    ),
                    retain=True,
                )

                pause()
                pause()

                assert calc.processor.od_normalization_factors == {"2": 0.8, "1": 0.5}
                assert calc.processor.od_blank == {"2": 0.4, "1": 0.25}
                results = calc.processor.scale_raw_observations(
                    create_od_raw_batched(
                        ["1", "2"], [0.6, 1.0], ["90", "90"], timestamp="2010-01-01T12:03:00.000Z"
                    )
                )
                assert results is not None
                assert abs(results["2"] - 1.5) < 0.00001
                assert abs(results["1"] - 1.4) < 0.00001

    def test_od_blank_being_higher_than_observations(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_higher_than_observations"
        with local_persistent_storage("od_blank") as cache:
            cache[experiment] = json.dumps({"1": 0.25, "2": 0.4})

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

        od_stream, dosing_stream = create_od_stream_from_mqtt(
            unit, experiment
        ), create_dosing_stream_from_mqtt(unit, experiment)

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)
            pause()

            pause()
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_encoded_od_raw_batched(
                    ["1", "2"], [0.50, 0.80], ["90", "135"], timestamp="2010-01-01T12:02:00.000Z"
                ),
                retain=True,
            )
            pause()
            pause()
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_encoded_od_raw_batched(
                    ["1", "2"], [0.1, 0.1], ["90", "135"], timestamp="2010-01-01T12:02:05.000Z"
                ),
                retain=True,
            )
            pause()
            pause()
            pause()
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_encoded_od_raw_batched(
                    ["1", "2"], [0.1, 0.1], ["90", "135"], timestamp="2010-01-01T12:02:10.000Z"
                ),
                retain=True,
            )
            pause()
            pause()

    def test_od_blank_being_empty(self) -> None:
        unit = get_unit_name()
        experiment = "test_od_blank_being_empty"

        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "90"),
                ("od_config.photodiode_channel", "2", "135"),
            ],
        ):
            with local_persistent_storage("od_blank") as cache:
                if experiment in cache:
                    del cache[experiment]

            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"1": 0.5, "2": 0.8})

            with local_persistent_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps({"1": 1e-6, "2": 1e-4})

            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_encoded_od_raw_batched(
                    ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01T12:02:10.000Z"
                ),
                retain=True,
            )

            od_stream = create_od_stream_from_mqtt(unit, experiment)
            dosing_stream = create_dosing_stream_from_mqtt(unit, experiment)
            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                pause()

                pause()
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01T12:02:15.000Z"
                    ),
                    retain=True,
                )
                pause()
                pause()
                assert calc.processor.od_normalization_factors == {"2": 0.8, "1": 0.5}
                assert calc.processor.od_blank == {"2": 0.0, "1": 0.0}
                results = calc.processor.scale_raw_observations(
                    create_od_raw_batched(
                        ["1", "2"], [0.6, 1.0], ["90", "90"], timestamp="2010-01-01T12:02:16.000Z"
                    )
                )
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

        od_stream = create_od_stream_from_mqtt(unit, experiment)
        dosing_stream = create_dosing_stream_from_mqtt(unit, experiment)

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                create_encoded_od_raw_batched(
                    ["2", "1"], [0.9, 1.1], ["135", "90"], timestamp="2010-01-01T12:00:00.000Z"
                ),
                retain=True,
            )

            assert calc.processor.scale_raw_observations(
                create_od_raw_batched(
                    ["1", "2"], [0.5, 2.0], ["90", "90"], timestamp="2010-01-01T12:03:00.000Z"
                )
            ) == {
                "1": 0.25,
                "2": 2.0,
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

        od_stream = create_od_stream_from_mqtt(unit, experiment)
        with collect_all_logs_of_level("ERROR", unit, experiment) as bucket:
            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, EmptyDosingSource())
                pause()
                pause()
                assert len(bucket) > 0

    @pytest.mark.slow
    def test_single_outlier_spike_gets_absorbed(self) -> None:
        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "REF"),
                ("od_config.photodiode_channel", "2", "90"),
                ("od_reading.config", "samples_per_second", "0.2"),
            ],
        ):
            unit = get_unit_name()
            experiment = "test_single_outlier_spike_gets_absorbed"

            # clear mqtt
            publish(
                f"pioreactor/{unit}/{experiment}/od_reading/ods",
                None,
                retain=True,
            )
            var = 1e-6
            std = float(np.sqrt(var))
            baseline = 0.05

            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"2": baseline})

            with local_persistent_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps({"2": var})

            od_stream, dosing_stream = (
                create_od_stream_from_mqtt(unit, experiment),
                create_dosing_stream_from_mqtt(unit, experiment),
            )

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                for _ in range(25):
                    v = baseline + std * np.random.randn()
                    t = current_utc_timestamp()
                    ods = create_od_raw_batched(["2"], [v], ["90"], timestamp=t)
                    calc.publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        encode(ods),
                        retain=True,
                    )
                    calc.publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/od2",
                        encode(ods.ods["2"]),
                        retain=True,
                    )
                    time.sleep(0.5)

                previous_nOD = calc.od_filtered
                previous_gr = calc.growth_rate
                # EKF is warmed up, introduce outlier. This outlier is "expected", given the smoothing we do.
                v = 2 * baseline + std * np.random.randn()
                t = current_utc_timestamp()
                ods = create_od_raw_batched(["2"], [v], ["90"], timestamp=t)
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    encode(ods),
                    retain=True,
                )
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od2",
                    encode(ods.ods["2"]),
                    retain=True,
                )

                # publish another minor outlier
                v = 1.2 * baseline + std * np.random.randn()
                t = current_utc_timestamp()
                ods = create_od_raw_batched(["2"], [v], ["90"], timestamp=t)
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    encode(ods),
                    retain=True,
                )
                calc.publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/od2",
                    encode(ods.ods["2"]),
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
                    ods = create_od_raw_batched(["2"], [v], ["90"], timestamp=t)
                    calc.publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        encode(ods),
                        retain=True,
                    )
                    calc.publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/od2",
                        encode(ods.ods["2"]),
                        retain=True,
                    )
                    time.sleep(0.5)

                # reverts back to previous
                current_nOD = calc.od_filtered
                current_gr = calc.growth_rate

                assert abs(previous_nOD.od_filtered - current_nOD.od_filtered) < 0.05
                assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

    def test_baseline_shift_gets_absorbed(self) -> None:
        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "REF"),
                ("od_config.photodiode_channel", "2", "90"),
                ("od_reading.config", "samples_per_second", "0.2"),
            ],
        ):
            unit = get_unit_name()
            experiment = "test_baseline_shift_gets_absorbed"

            var = 1e-6
            std = float(np.sqrt(var))

            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"2": 0.05})
            with local_persistent_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps({"2": var})

            od_stream, dosing_stream = (
                create_od_stream_from_mqtt(unit, experiment),
                create_dosing_stream_from_mqtt(unit, experiment),
            )

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                with create_client() as client:

                    def publish_and_wait(topic: str, payload, retain=False) -> None:
                        msg_info = client.publish(topic, payload, retain=retain)
                        msg_info.wait_for_publish()

                    # Initial steady data
                    for _ in range(30):
                        v = 0.05 + std * np.random.randn()
                        t = current_utc_timestamp()
                        publish_and_wait(
                            f"pioreactor/{unit}/{experiment}/od_reading/ods",
                            create_encoded_od_raw_batched(["2"], [v], ["90"], timestamp=t),
                        )
                        publish_and_wait(
                            f"pioreactor/{unit}/{experiment}/od_reading/od2",
                            encode(
                                structs.RawODReading(
                                    od=v,
                                    angle="90",
                                    timestamp=to_datetime(t),
                                    channel="2",
                                    ir_led_intensity=80,
                                )
                            ),
                        )
                        time.sleep(0.1)

                    previous_gr = calc.growth_rate

                    # Introduce baseline shift
                    shift = 0.01
                    calc.logger.info("OFFSET!")
                    for _ in range(30):
                        v = 0.05 + shift + std * np.random.randn()
                        t = current_utc_timestamp()
                        publish_and_wait(
                            f"pioreactor/{unit}/{experiment}/od_reading/ods",
                            create_encoded_od_raw_batched(["2"], [v], ["90"], timestamp=t),
                        )
                        publish_and_wait(
                            f"pioreactor/{unit}/{experiment}/od_reading/od2",
                            encode(
                                structs.RawODReading(
                                    od=v,
                                    angle="90",
                                    timestamp=to_datetime(t),
                                    channel="2",
                                    ir_led_intensity=80,
                                )
                            ),
                        )
                        time.sleep(0.1)

                current_gr = calc.growth_rate

                assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

    def test_massive_outlier_spike_gets_absorbed(self) -> None:
        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "REF"),
                ("od_config.photodiode_channel", "2", "90"),
                ("od_reading.config", "samples_per_second", "0.2"),
            ],
        ):
            unit = get_unit_name()
            experiment = "test_massive_outlier_spike_gets_absorbed"

            var = 1e-6
            std = float(np.sqrt(var))

            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"2": 0.05})
            with local_persistent_storage("od_normalization_variance") as cache:
                cache[experiment] = json.dumps({"2": var})

            od_stream, dosing_stream = (
                create_od_stream_from_mqtt(unit, experiment),
                create_dosing_stream_from_mqtt(unit, experiment),
            )

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)

                with create_client() as client:

                    def publish_and_wait(topic: str, payload, retain=False) -> None:
                        msg_info = client.publish(topic, payload, retain=retain)
                        msg_info.wait_for_publish()

                    for _ in range(30):
                        v = 0.05 + std * np.random.randn()
                        t = current_utc_timestamp()
                        publish_and_wait(
                            f"pioreactor/{unit}/{experiment}/od_reading/ods",
                            create_encoded_od_raw_batched(["2"], [v], ["90"], timestamp=t),
                            retain=True,
                        )
                        publish_and_wait(
                            f"pioreactor/{unit}/{experiment}/od_reading/od2",
                            encode(
                                structs.RawODReading(
                                    od=v,
                                    angle="90",
                                    timestamp=to_datetime(t),
                                    channel="2",
                                    ir_led_intensity=80,
                                )
                            ),
                            retain=True,
                        )
                        time.sleep(0.1)

                    previous_nOD = calc.od_filtered
                    previous_gr = calc.growth_rate

                    # introduce large outlier
                    v = 0.6 + std * np.random.randn()
                    t = current_utc_timestamp()
                    publish_and_wait(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        create_encoded_od_raw_batched(["2"], [v], ["90"], timestamp=t),
                        retain=True,
                    )
                    publish_and_wait(
                        f"pioreactor/{unit}/{experiment}/od_reading/od2",
                        encode(
                            structs.RawODReading(
                                od=v, angle="90", timestamp=to_datetime(t), channel="2", ir_led_intensity=80
                            )
                        ),
                        retain=True,
                    )
                    time.sleep(0.1)

                    current_nOD = calc.od_filtered
                    current_gr = calc.growth_rate

                    assert previous_nOD.od_filtered < current_nOD.od_filtered
                    assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

                    # resume normal values
                    for _ in range(30):
                        v = 0.05 + std * np.random.randn()
                        t = current_utc_timestamp()
                        publish_and_wait(
                            f"pioreactor/{unit}/{experiment}/od_reading/ods",
                            create_encoded_od_raw_batched(["2"], [v], ["90"], timestamp=t),
                            retain=True,
                        )
                        publish_and_wait(
                            f"pioreactor/{unit}/{experiment}/od_reading/od2",
                            encode(
                                structs.RawODReading(
                                    od=v,
                                    angle="90",
                                    timestamp=to_datetime(t),
                                    channel="2",
                                    ir_led_intensity=80,
                                )
                            ),
                            retain=True,
                        )
                        time.sleep(0.1)

                    current_nOD = calc.od_filtered
                    current_gr = calc.growth_rate

                    assert abs(previous_nOD.od_filtered - current_nOD.od_filtered) < 0.05
                    assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

    @pytest.mark.slow
    def test_abnormal_kf_caused_by_previous_outlier_algo(self) -> None:
        experiment = "test_abnormal_kf_caused_by_previous_outlier_algo"
        unit = "wk3"

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({"2": 0.2631887966203668})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[experiment] = json.dumps({"2": 1.165246946031255e-06})

        with local_persistent_storage("od_filtered") as cache:
            cache[experiment] = 1.00922563

        with temporary_config_changes(
            config,
            [
                ("growth_rate_kalman", "od_std", str(float(config["growth_rate_kalman"]["od_std"]) / 2)),
                ("growth_rate_calculating.config", "ekf_outlier_std_threshold", "3"),
            ],
        ):
            with ExportODSource(
                "./core/tests/data/od_readings_with_too_frequently_outlier_detections.csv",
                skip_first=40,
            ) as od_stream, ExportDosingSource(None) as dosing_stream, GrowthRateCalculator(
                unit=unit, experiment=experiment
            ) as calc:
                for _, result in enumerate(
                    calc.process_until_disconnected_or_exhausted(od_stream, dosing_stream)
                ):
                    if result[1].od_filtered <= 0:
                        assert False
                        break

                assert True
