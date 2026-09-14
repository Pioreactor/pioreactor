# -*- coding: utf-8 -*-
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from msgspec.json import decode
from msgspec.json import encode
from pioreactor import hardware
from pioreactor import structs
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.od_devices import register_od_device
from pioreactor.structs import ODDeviceReading
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_unit_name


@pytest.fixture
def external_source(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    reader = MagicMock()
    reader.signal_unit = "ratio"
    reader.source = "test_probe"
    reader.read.return_value = ODDeviceReading(timestamp=current_utc_datetime(), value=7.4e-7)
    register_od_device("test_probe", lambda hardware, logger: reader)
    monkeypatch.setattr(
        hardware,
        "get_od_hardware_config",
        lambda *args: hardware.ODHardwareConfig(driver="test_probe", address=0x69),
    )
    return reader


def test_external_source_uses_native_job_without_photodiodes(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor.background_jobs.od_reading import ADCReader

    monkeypatch.setattr(
        ADCReader, "__init__", MagicMock(side_effect=AssertionError("ADC must not be initialized"))
    )
    with start_od_reading({}, unit=get_unit_name(), experiment="test_source", interval=None) as job:
        assert isinstance(job, ODReader)
        assert job.job_name == "od_reading"
        assert job.acquisition == "continuous"
        assert "first_od_obs_time" not in job.published_settings
        reading = job.record()
        assert reading is not None
        decoded = decode(encode(reading), type=structs.ODReadings)
        assert isinstance(decoded.ods["1"], structs.SensorODReading)
        assert decoded.ods["1"].od == 7.4e-7
        assert decoded.ods["1"].angle == "0"
        job.set_state(job.SLEEPING)
        external_source.stop.assert_called_once()
        assert job.record() is None
        job.set_state(job.READY)
        assert external_source.start.call_count == 2
    external_source.close.assert_called_once()


def test_source_start_failure_closes_driver(external_source: MagicMock) -> None:
    external_source.start.side_effect = OSError("start failed")
    with pytest.raises(OSError, match="start failed"):
        start_od_reading({}, unit=get_unit_name(), experiment="test_start_fail", interval=None)
    external_source.close.assert_called_once()


def test_no_new_sample_and_invalid_sample(external_source: MagicMock) -> None:
    with start_od_reading({}, unit=get_unit_name(), experiment="test_samples", interval=None) as job:
        external_source.read.return_value = None
        assert job.record() is None
        assert job.ods is None
        with pytest.raises(ValueError, match="invalid observation"):
            ODDeviceReading(timestamp=current_utc_datetime(), value=float("nan"))
        assert job.ods is None


def test_external_blank_is_rejected_before_measurement(external_source: MagicMock) -> None:
    from pioreactor.actions.od_blank import od_blank

    with pytest.raises(Exception, match="not supported"):
        od_blank(unit=get_unit_name(), experiment="test_blank_source")
    external_source.start.assert_not_called()


def test_dodging_is_disabled_for_external_source(external_source: MagicMock) -> None:
    from pioreactor.background_jobs.base import BackgroundJobWithDodging
    from pioreactor.states import JobState

    # The decision is independent of a running timer or hardware state.
    assert not BackgroundJobWithDodging._desired_dodging_mode(None, True, JobState.READY)


def test_external_source_ignores_photodiode_fusion(external_source: MagicMock) -> None:
    from pioreactor.background_jobs.growth_rate_calculating import _should_use_fused_od

    assert not _should_use_fused_od(get_unit_name())


def test_hardware_layering_keeps_aux_but_replaces_pd_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hardware, "get_dot_pioreactor_path", lambda: tmp_path)
    monkeypatch.setattr(hardware, "hardware_version_info", (1, 2))
    hat = tmp_path / "hardware/hats/1.2"
    model = tmp_path / "hardware/models/pioreactor_40ml/1.5"
    hat.mkdir(parents=True)
    model.mkdir(parents=True)
    (hat / "adc.yaml").write_text(
        "aux: {driver: pico, address: 44, channel: 1}\npd1: {driver: ads1114, address: 72, channel: 0}\n",
        encoding="utf-8",
    )
    assert hardware.get_od_hardware_config("pioreactor_40ml", "1.5").driver == "photodiodes"
    assert hardware.get_required_i2c_addresses_for_model("pioreactor_40ml", "1.5") == {44, 72}
    (model / "od.yaml").write_text("driver: test_probe\nbus: 1\naddress: 0x69\n", encoding="utf-8")
    assert hardware.get_required_i2c_addresses_for_model("pioreactor_40ml", "1.5") == {44, 105}


def test_unknown_source_never_falls_back_to_adc(monkeypatch: pytest.MonkeyPatch) -> None:
    from pioreactor.od_devices import create_od_device
    from pioreactor import plugin_management

    monkeypatch.setattr(plugin_management, "get_plugins", lambda: {})
    with pytest.raises(Exception, match="not installed"):
        create_od_device(hardware.ODHardwareConfig(driver="missing", address=0x69), MagicMock())


def test_backscatter_round_trips_through_existing_od_table() -> None:
    import sqlite3
    from pioreactor.background_jobs.leader.mqtt_to_db_streaming import parse_od
    from pioreactor.utils.timing import current_utc_datetime

    reading = structs.SensorODReading(
        timestamp=current_utc_datetime(), od=7.45279e-7, channel="1", source="test_probe", signal_unit="ratio"
    )
    row = parse_od("pioreactor/unit/experiment/od_reading/od1", encode(reading))
    assert row["angle"] == 0
    connection = sqlite3.connect(":memory:")
    schema = (Path(__file__).parents[2] / "packaging/shared-assets/sql/create_tables.sql").read_text(
        encoding="utf-8"
    )
    connection.executescript(schema)
    columns = ",".join(row)
    connection.execute(
        f"INSERT INTO od_readings ({columns}) VALUES ({','.join('?' for _ in row)})", tuple(row.values())
    )
    stored = connection.execute("SELECT angle,od_reading FROM od_readings").fetchone()
    assert stored == (0, 7.45279e-7)
    connection.close()


def test_self_tests_skip_photodiode_operations(external_source: MagicMock) -> None:
    from pioreactor.actions.self_test import get_builtin_self_tests

    names = {test.__name__ for test in get_builtin_self_tests()}
    assert "test_REF_is_in_correct_position" not in names
    assert "test_positive_correlation_between_rpm_and_stirring" in names


def test_probe_mqtt_reaches_native_growth_model(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    import math
    from datetime import timedelta
    from threading import Thread
    from pioreactor.config import config
    from pioreactor.config import temporary_config_changes
    from pioreactor.utils.timing import current_utc_datetime
    from .utils import wait_for

    experiment = "test_probe_native_growth"
    monkeypatch.setattr(
        "pioreactor.background_jobs.growth_rate_calculating.INITIAL_OD_OBSERVATIONS_TO_SKIP", 0
    )
    timestamp = current_utc_datetime()
    with temporary_config_changes(
        config, [("growth_rate_calculating.config", "samples_for_od_statistics", "5")]
    ):
        with GrowthRateCalculator(get_unit_name(), experiment) as calc:
            processing = Thread(target=calc.block_until_disconnected, daemon=True)
            processing.start()
            try:
                with start_od_reading({}, unit=get_unit_name(), experiment=experiment, interval=None) as job:
                    for index in range(10):
                        timestamp += timedelta(seconds=5)
                        external_source.read.return_value = ODDeviceReading(
                            timestamp=timestamp, value=7.4e-7 * (1.001**index)
                        )
                        job.record()
                    assert wait_for(
                        lambda: calc.growth_rate is not None and calc.od_filtered is not None, timeout=5.0
                    )
                    assert calc.od_filtered is not None
                    assert math.isfinite(calc.growth_rate.growth_rate)
                    assert 0.9 < calc.od_filtered.od_filtered < 1.1
            finally:
                calc._blocking_event.set()
                processing.join(timeout=2.0)
                with local_persistent_storage("od_normalization_mean") as cache:
                    cache.pop(experiment, None)
            assert not processing.is_alive()


def test_device_preserves_acquisition_time_and_uses_one_backscatter_channel(
    external_source: MagicMock,
) -> None:
    timestamp = current_utc_datetime()
    external_source.read.return_value = ODDeviceReading(timestamp=timestamp, value=0.5)
    with start_od_reading({}, unit=get_unit_name(), experiment="device_outputs", interval=None) as job:
        batch = job.record()
        assert batch.timestamp == timestamp
        assert set(batch.ods) == {"1"}
        assert job.od1.od == 0.5
        assert job.od1.angle == "0"
        assert "raw_od1" not in job.published_settings
        assert "first_od_obs_time" not in job.published_settings
