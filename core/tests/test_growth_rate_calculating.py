# -*- coding: utf-8 -*-
import json
import subprocess
import sys
import time
from collections.abc import Iterator
from threading import Thread
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from msgspec.json import encode
from pioreactor import structs
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.config import config
from pioreactor.config import temporary_config_changes
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.job_manager import JobManager
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


def block_until_disconnected_in_background(calc: GrowthRateCalculator) -> Thread:
    def block_without_skipping_startup_observations() -> None:
        with patch(
            "pioreactor.background_jobs.growth_rate_calculating.INITIAL_OD_OBSERVATIONS_TO_SKIP",
            0,
        ):
            calc.block_until_disconnected()

    thread = Thread(target=block_without_skipping_startup_observations, daemon=True)
    thread.start()
    return thread


def stop_background_processing(calc: GrowthRateCalculator, thread: Thread) -> None:
    calc._blocking_event.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()


class TestGrowthRateCalculating:
    @classmethod
    def setup_class(cls) -> None:
        with local_persistent_storage("od_normalization_mean") as cache:
            for experiment in cache.iterkeys():
                del cache[experiment]

    def setup_method(self) -> None:
        with JobManager() as job_manager:
            job_manager.clear()

    def test_module_import_does_not_require_grpredict(self) -> None:
        subprocess.run(
            [
                sys.executable,
                "-c",
                """
import builtins

real_import = builtins.__import__


def import_without_grpredict(name, *args, **kwargs):
    if name == "grpredict" or name.startswith("grpredict."):
        raise ModuleNotFoundError("grpredict is unavailable on leader-only installs")
    return real_import(name, *args, **kwargs)


builtins.__import__ = import_without_grpredict
import pioreactor.background_jobs.growth_rate_calculating
""",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @pytest.mark.parametrize(
        ("section", "option", "value", "error"),
        [
            (
                "od_reading.config",
                "samples_per_second",
                "0",
                r"samples_per_second=0\.0",
            ),
            (
                "growth_rate_calculating.config",
                "samples_for_od_statistics",
                "0",
                "samples_for_od_statistics=0",
            ),
            (
                "growth_rate_calculating.config",
                "ekf_outlier_std_threshold",
                "2",
                r"ekf_outlier_std_threshold=2\.0",
            ),
        ],
    )
    def test_invalid_required_configuration_fails_before_startup(
        self,
        section: str,
        option: str,
        value: str,
        error: str,
    ) -> None:
        with temporary_config_changes(config, [(section, option, value)]):
            with pytest.raises(ValueError, match=error):
                GrowthRateCalculator(
                    unit=get_unit_name(),
                    experiment="test_invalid_required_configuration_fails_before_startup",
                )

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
                processing_thread = block_until_disconnected_in_background(calc1)
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
                assert wait_for(lambda: calc1.growth_rate is not None, timeout=10.0)
                stop_background_processing(calc1, processing_thread)

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc2:
                processing_thread = block_until_disconnected_in_background(calc2)
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
                assert wait_for(lambda: calc2.growth_rate is not None, timeout=3.0)
                stop_background_processing(calc2, processing_thread)

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

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                processing_thread = block_until_disconnected_in_background(calc)

                first_od_payload = create_encoded_od_raw_batched(
                    ["1"],
                    [0.51],
                    ["90"],
                    timestamp="2010-01-01T12:00:40.000Z",
                )

                for _ in range(10):
                    publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        first_od_payload,
                    )
                    if wait_for(lambda: calc.ekf is not None, timeout=1.0):
                        break

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
                    if wait_for(lambda: calc._post_dose_observations_remaining > 0, timeout=2.0):
                        break

                assert calc._post_dose_observations_remaining > 0

                for i in range(10):
                    post_dose_od_payload = create_encoded_od_raw_batched(
                        ["1"],
                        [0.40],
                        ["90"],
                        timestamp=f"2010-01-01T12:02:{i:02d}.000Z",
                    )
                    publish(
                        f"pioreactor/{unit}/{experiment}/od_reading/ods",
                        post_dose_od_payload,
                    )
                    if wait_for(lambda: calc._post_dose_observations_remaining == 0, timeout=5.0):
                        break

                assert calc._post_dose_observations_remaining == 0
                stop_background_processing(calc, processing_thread)

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

            with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                processing_thread = block_until_disconnected_in_background(calc)

                time.sleep(35)

                assert calc.ekf.state_[1] > 0
                stop_background_processing(calc, processing_thread)

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

    def test_post_dose_reset_window_is_exactly_two_successful_observations(self) -> None:
        reading = create_od_raw_batched(
            ["1"],
            [1.0],
            ["90"],
            timestamp="2010-01-01T12:03:00.000Z",
        )

        with GrowthRateCalculator(
            unit=get_unit_name(),
            experiment="test_post_dose_reset_window_is_exactly_two_successful_observations",
        ) as calc:
            calc.od_normalization_factors = {"1": 1.0}
            calc.ekf = MagicMock()
            calc.ekf.update.return_value = ([0.0, 0.0, 0.0], None)
            calc._post_dose_observations_remaining = 2

            calc._update_state_from_observation(reading)
            calc._update_state_from_observation(reading)
            calc._update_state_from_observation(reading)

            assert [args.args[2] for args in calc.ekf.update.call_args_list] == [
                True,
                True,
                False,
            ]
            assert calc._post_dose_observations_remaining == 0

    def test_dosing_during_warmup_restarts_observation_collection(self) -> None:
        unit = get_unit_name()
        experiment = "test_dosing_during_warmup_restarts_observation_collection"
        before_dose = create_od_raw_batched(["1"], [0.5], ["90"], timestamp="2010-01-01T12:00:00.000Z")
        dosing_event = structs.DosingEvent(
            volume_change=1.0,
            event="add_media",
            source_of_event="test",
            timestamp=to_datetime("2010-01-01T12:00:01.000Z"),
        )
        after_dose = [
            create_od_raw_batched(["1"], [0.4], ["90"], timestamp="2010-01-01T12:00:02.000Z"),
            create_od_raw_batched(["1"], [0.41], ["90"], timestamp="2010-01-01T12:00:03.000Z"),
        ]

        with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
            calc.samples_for_od_statistics = 2
            events = iter([before_dose, dosing_event, *after_dose])
            warmup_events = calc.collect_warmup_events(events)

        assert warmup_events == after_dose
        assert list(events) == []

    def test_shutdown_during_warmup_without_observations_is_clean(self) -> None:
        with GrowthRateCalculator(
            unit=get_unit_name(),
            experiment="test_shutdown_during_warmup_without_observations_is_clean",
        ) as calc:
            calc._blocking_event.set()

            calc.block_until_disconnected()

            assert calc.ekf is None

    def test_shutdown_during_warmup_does_not_initialize_from_partial_observations(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reading = create_od_raw_batched(
            ["1"],
            [0.5],
            ["90"],
            timestamp="2010-01-01T12:00:00.000Z",
        )

        with GrowthRateCalculator(
            unit=get_unit_name(),
            experiment="test_shutdown_during_warmup_does_not_initialize_from_partial_observations",
        ) as calc:

            def stop_after_one_reading() -> Iterator[structs.ODReadings | structs.DosingEvent]:
                yield reading
                calc._blocking_event.set()

            initialize_filter = MagicMock(
                side_effect=AssertionError("The filter must not initialize after shutdown.")
            )
            monkeypatch.setattr(calc, "stream_mqtt_growth_rate_events", stop_after_one_reading)
            monkeypatch.setattr(calc, "_initialize_extended_kalman_filter", initialize_filter)

            calc.block_until_disconnected()

            assert calc.ekf is None
            initialize_filter.assert_not_called()

    def test_event_stream_exhaustion_is_not_a_supported_lifecycle(self) -> None:
        experiment = "test_event_stream_exhaustion_is_not_a_supported_lifecycle"
        reading = create_od_raw_batched(
            ["1"],
            [0.5],
            ["90"],
            timestamp="2010-01-01T12:00:00.000Z",
        )

        with temporary_config_changes(
            config,
            [("growth_rate_calculating.config", "samples_for_od_statistics", "1")],
        ):
            with local_persistent_storage("od_normalization_mean") as cache:
                cache[experiment] = json.dumps({"1": 0.5})

            with GrowthRateCalculator(unit=get_unit_name(), experiment=experiment) as calc:
                with patch.object(
                    calc,
                    "stream_mqtt_growth_rate_events",
                    return_value=iter([reading]),
                ):
                    with pytest.raises(RuntimeError, match="stopped before job shutdown"):
                        calc.block_until_disconnected()

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

            reading = create_od_raw_batched(
                ["1"],
                [0.0],
                ["90"],
                timestamp="2010-01-01T12:00:35.000Z",
            )
            with collect_all_logs_of_level("ERROR", unit, experiment) as bucket:
                with GrowthRateCalculator(unit=unit, experiment=experiment) as calc:
                    with patch.object(
                        calc,
                        "stream_mqtt_growth_rate_events",
                        return_value=iter([reading]),
                    ):
                        with pytest.raises(ValueError, match="Non-positive OD normalization factor"):
                            calc.block_until_disconnected()

                    assert wait_for(lambda: len(bucket) > 0, timeout=5.0)

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
