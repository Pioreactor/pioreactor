# -*- coding: utf-8 -*-
import json
import time
from threading import Event
from typing import Iterator

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
from pioreactor.utils.job_manager import JobManager
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


class EmptyLiveDosingSource:
    is_live = True

    def __iter__(self) -> Iterator[structs.DosingEvent]:
        return iter(())

    def set_stop_event(self, ev: Event) -> None:
        return None


class TestGrowthRateCalculating:
    @classmethod
    def setup_class(cls) -> None:
        with local_persistent_storage("od_normalization_mean") as cache:
            for experiment in cache.iterkeys():
                del cache[experiment]

    def setup_method(self) -> None:
        with JobManager() as job_manager:
            job_manager.clear()

    @pytest.mark.slow
    def test_subscribing(self) -> None:
        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "90"),
                ("od_config.photodiode_channel", "2", "90"),
                ("growth_rate_calculating.config", "samples_for_od_statistics", "1"),
            ],
        ):
            unit = get_unit_name()
            experiment = "test_subscribing"

            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({1: 1.0, 2: 1.0})

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
                assert wait_for(lambda: calc.ekf is not None, timeout=5.0)
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

                assert calc.ekf is not None

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

                assert calc.ekf.state_ is not None

    @pytest.mark.flakey
    def test_restart(self) -> None:
        unit = get_unit_name()
        experiment = "test_restart"

        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "90"),
                ("od_config.photodiode_channel", "2", "90"),
                ("growth_rate_calculating.config", "samples_for_od_statistics", "1"),
            ],
        ):
            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"1": 1.15, "2": 0.93})

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc1:
                od_stream, dosing_stream = create_od_stream_from_mqtt(
                    unit, experiment
                ), create_dosing_stream_from_mqtt(unit, experiment)
                calc1.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)
                pause()

                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.151, 0.931],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:20.000Z",
                    ),
                )
                assert wait_for(lambda: calc1.ekf is not None, timeout=5.0)
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
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.155, 0.935],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:35.000Z",
                    ),
                )
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.156, 0.936],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:35.000Z",
                    ),
                )
                assert wait_for(lambda: calc1.kalman_filter_outputs is not None, timeout=10.0)

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc2:
                od_stream, dosing_stream = create_od_stream_from_mqtt(
                    unit, experiment
                ), create_dosing_stream_from_mqtt(unit, experiment)

                calc2.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)
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
                assert wait_for(lambda: calc2.ekf is not None, timeout=5.0)
                publish(
                    f"pioreactor/{unit}/{experiment}/od_reading/ods",
                    create_encoded_od_raw_batched(
                        ["1", "2"],
                        [1.155, 0.935],
                        ["90", "135"],
                        timestamp="2010-01-01T12:00:40.000Z",
                    ),
                )
                assert wait_for(lambda: calc2.kalman_filter_outputs is not None, timeout=3.0)

    def test_scaling_works(self) -> None:
        experiment = "test_scaling_works"

        with GrowthRateCalculator(unit=get_unit_name(), experiment=experiment) as calc:
            calc.od_normalization_factors = {"1": 0.5, "2": 0.8}
            assert calc.od_normalization_factors == {"2": 0.8, "1": 0.5}
            assert calc.scale_raw_observations(
                create_od_raw_batched(
                    ["1", "2"], [0.5, 0.8], ["90", "135"], timestamp="2010-01-01T12:00:35.000Z"
                )
            ) == {"2": 1.0, "1": 1.0}

    @pytest.mark.slow
    def test_shock_from_dosing_works(self) -> None:
        unit = get_unit_name()
        experiment = "test_shock_from_dosing_works"

        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "90"),
                ("od_config.photodiode_channel", "2", "REF"),
                ("growth_rate_calculating.config", "samples_for_od_statistics", "1"),
            ],
        ):
            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"1": 0.5})

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
                assert wait_for(lambda: calc.ekf is not None, timeout=5.0)

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

                dosing_event_payload = encode(
                    structs.DosingEvent(
                        volume_change=1.0,
                        event="add_media",
                        source_of_event="algo",
                        timestamp=to_datetime("2010-01-01T12:01:55.000Z"),
                    )
                )

                for _ in range(3):
                    publish(
                        f"pioreactor/{unit}/{experiment}/dosing_events",
                        dosing_event_payload,
                    )
                    if wait_for(lambda: calc._recent_dilution, timeout=2.0):
                        break

                assert calc._recent_dilution

                post_dose_od_payload = create_encoded_od_raw_batched(
                    ["1"],
                    [0.40],
                    ["90"],
                    timestamp="2010-01-01T12:02:00.000Z",
                )

                for _ in range(3):
                    publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        post_dose_od_payload,
                    )
                    if wait_for(lambda: not calc._recent_dilution, timeout=2.0):
                        break

                assert not calc._recent_dilution

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

                assert calc.ekf.state_[1] > 0

            thread.cancel()

    def test_observation_order_is_preserved_in_job(self) -> None:
        unit = get_unit_name()
        experiment = "test_observation_order_is_preserved_in_job"

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            calc.od_normalization_factors = {"1": 2, "2": 1}

            assert calc.scale_raw_observations(
                create_od_raw_batched(
                    ["1", "2"], [0.5, 2.0], ["90", "90"], timestamp="2010-01-01T12:03:00.000Z"
                )
            ) == {
                "1": 0.25,
                "2": 2.0,
            }

    def test_zero_reference_and_zero_od_coming_in(self) -> None:
        unit = get_unit_name()
        experiment = "test_zero_reference_and_zero_od_coming_in"
        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "90"),
                ("od_config.photodiode_channel", "2", None),
                ("growth_rate_calculating.config", "samples_for_od_statistics", "1"),
            ],
        ):
            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"1": 0})

            od_stream = create_od_stream_from_mqtt(unit, experiment)
            with collect_all_logs_of_level("ERROR", unit, experiment) as bucket:
                with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                    calc.process_until_disconnected_or_exhausted_in_background(
                        od_stream, EmptyLiveDosingSource()
                    )
                    pause()
                    publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        create_encoded_od_raw_batched(
                            ["1"],
                            [0.0],
                            ["90"],
                            timestamp="2010-01-01T12:00:35.000Z",
                        ),
                        retain=True,
                    )
                    assert wait_for(lambda: len(bucket) > 0, timeout=5.0)

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

    @pytest.mark.xfail
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

    @pytest.mark.slow
    def test_massive_outlier_spike_gets_absorbed(self) -> None:
        with temporary_config_changes(
            config,
            [
                ("od_config.photodiode_channel", "1", "REF"),
                ("od_config.photodiode_channel", "2", "90"),
                ("od_reading.config", "samples_per_second", "0.2"),
                ("growth_rate_calculating.config", "samples_for_od_statistics", "1"),
            ],
        ):
            unit = get_unit_name()
            experiment = "test_massive_outlier_spike_gets_absorbed"

            var = 1e-6
            std = float(np.sqrt(var))

            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"2": 0.05})

            od_stream, dosing_stream = (
                create_od_stream_from_mqtt(unit, experiment),
                create_dosing_stream_from_mqtt(unit, experiment),
            )

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                calc.process_until_disconnected_or_exhausted_in_background(od_stream, dosing_stream)
                pause()

                def publish_observation(value: float) -> None:
                    t = current_utc_timestamp()
                    ods = create_od_raw_batched(["2"], [value], ["90"], timestamp=t)
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

                for _ in range(25):
                    publish_observation(0.05 + std * np.random.randn())
                    pause()

                assert wait_for(lambda: calc.od_filtered is not None and calc.growth_rate is not None)
                previous_nOD = calc.od_filtered
                previous_gr = calc.growth_rate

                publish_observation(0.6 + std * np.random.randn())
                pause()

                current_nOD = calc.od_filtered
                current_gr = calc.growth_rate

                assert previous_nOD.od_filtered < current_nOD.od_filtered
                assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

                for _ in range(30):
                    publish_observation(0.05 + std * np.random.randn())
                    pause()

                current_nOD = calc.od_filtered
                current_gr = calc.growth_rate

                assert abs(previous_nOD.od_filtered - current_nOD.od_filtered) < 0.05
                assert abs(previous_gr.growth_rate - current_gr.growth_rate) < 0.01

    def test_empty_cached_normalization_dicts_are_recomputed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        experiment = "test_empty_cached_normalization_dicts_are_recomputed"
        unit = get_unit_name()
        expected_means = {"2": 1.23}
        expected_variances = {"2": 1e-6}

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[experiment] = json.dumps({})

        warmup_events: list[structs.ODReadings] = []

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            monkeypatch.setattr(
                calc,
                "_compute_od_statistics_from_warmup_events",
                lambda _: (expected_means, expected_variances),
            )

            means = calc._get_precomputed_normalization_factors(warmup_events)

        assert means == expected_means

    def test_obs_noise_covariance_uses_same_channel_order_as_live_updates(self) -> None:
        experiment = "test_obs_noise_covariance_uses_same_channel_order_as_live_updates"
        unit = get_unit_name()

        warmup_observations = [
            {"1": 1.00, "2": 1.000},
            {"1": 1.35, "2": 1.002},
            {"1": 0.82, "2": 0.998},
            {"1": 1.42, "2": 1.001},
            {"1": 0.76, "2": 0.999},
        ]

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            calc.od_normalization_factors = {"1": 1.0, "2": 1.0}

            covariance = calc._create_obs_noise_covariance_from_warmup_observations(warmup_observations)
            live_reading = create_od_raw_batched(
                ["1", "2"],
                [1.1, 1.0],
                ["90", "135"],
                timestamp="2010-01-01T12:00:01.000Z",
            )
            scaled_live = calc.scale_raw_observations(live_reading)

        assert list(scaled_live) == ["2", "1"]
        assert covariance[0, 0] < covariance[1, 1]
