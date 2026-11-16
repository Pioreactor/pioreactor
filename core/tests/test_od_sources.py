# -*- coding: utf-8 -*-
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from msgspec.json import decode
from msgspec.json import encode
from pioreactor import exc
from pioreactor import hardware
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.od_reading import ExternalODReader
from pioreactor.background_jobs.od_reading import start_external_od_reading
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.od_devices import od_calibration_device
from pioreactor.od_devices import register_od_device
from pioreactor.structs import ODDeviceReadings
from pioreactor.structs import ODSignal
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_unit_name

REFLECTANCE = ODSignal(name="reflectance", angle="0", scale="reflectance ratio, v1")
DENSITY = ODSignal(name="density", angle="0", scale="g/L, v1", calibrated=True)
FLUORESCENCE = ODSignal(name="fluorescence", angle="90", scale="counts, gain 4")


def _readings(*values: float, timestamp: datetime | None = None) -> ODDeviceReadings:
    """Values for channels 1, 2, ... in order."""
    return ODDeviceReadings(
        timestamp=timestamp or current_utc_datetime(),
        values={str(index): value for index, value in enumerate(values, start=1)},  # type: ignore[misc]
    )


@pytest.fixture
def external_source(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    import pioreactor.calibrations as calibrations

    device = MagicMock()
    device.outputs = {"1": REFLECTANCE}
    device.read.return_value = _readings(7.4e-7)
    register_od_device("test_probe", lambda options, logger: device)
    monkeypatch.setattr(
        hardware,
        "get_od_hardware_config",
        lambda *args: hardware.ODHardwareConfig(driver="test_probe", options={"address": 0x69}),
    )
    # Tests opt into active calibrations explicitly.
    monkeypatch.setattr(calibrations, "load_active_calibration", lambda device: None)
    yield device


def _calibration(
    signal: ODSignal = REFLECTANCE, driver: str = "test_probe", name: str = "probe-standards"
) -> structs.ExternalODCalibration:
    # signal = 0.2 * OD600 + 0.05
    return structs.ExternalODCalibration(
        calibration_name=name,
        calibrated_on_pioreactor_unit=get_unit_name(),
        created_at=current_utc_datetime(),
        curve_data_=structs.PolyFitCoefficients(coefficients=[0.2, 0.05]),
        recorded_data={"x": [0.0, 1.0, 2.0], "y": [0.05, 0.25, 0.45]},
        driver=driver,
        signal=signal.name,
        signal_scale=signal.scale,
    )


def _activate(monkeypatch: pytest.MonkeyPatch, active: dict[str, Any]) -> list[str]:
    """Serve `active` as the active calibrations by device, recording each lookup."""
    import pioreactor.calibrations as calibrations

    requested: list[str] = []

    def load_active_calibration(device: str) -> Any:
        requested.append(device)
        return active.get(device)

    monkeypatch.setattr(calibrations, "load_active_calibration", load_active_calibration)
    return requested


# --- published shape


@pytest.mark.parametrize("calibrated", [0, 1])
def test_develop_od_payload_decodes_with_integer_calibration_flag(calibrated: int) -> None:
    payload = {
        "timestamp": "2026-09-01T01:00:00Z",
        "od": 0.42,
        "channel": "1",
        "angle": "90",
        "calibrated": calibrated,
        "ir_led_intensity": 70.0,
    }
    if calibrated:
        payload["calibration_name"] = "test_calibration"
    reading = decode(encode(payload), type=structs.ODReading)
    batch = decode(
        encode({"timestamp": payload["timestamp"], "ods": {"1": payload}}), type=structs.ODReadings
    )
    assert batch.ods["1"] == reading
    published = decode(encode(reading))
    assert type(published["calibrated"]) is int
    assert published["calibrated"] == calibrated
    assert set(published) == {"timestamp", "od", "channel", "angle", "calibrated"}


@pytest.mark.parametrize("calibrated", [2, -1, True, False])
def test_od_payload_rejects_invalid_calibration_flag(calibrated: int | bool) -> None:
    from msgspec import ValidationError

    payload = {
        "timestamp": "2026-09-01T01:00:00Z",
        "od": 0.42,
        "channel": "1",
        "angle": "90",
        "calibrated": calibrated,
    }
    with pytest.raises(ValidationError):
        decode(encode(payload), type=structs.ODReading)


def test_device_readings_require_timezone_and_finite_values() -> None:
    with pytest.raises(ValueError, match="timezone"):
        ODDeviceReadings(timestamp=datetime(2026, 1, 1), values={"1": 0.1})
    with pytest.raises(ValueError, match="invalid observation on channel 1"):
        _readings(float("nan"))


def test_calibration_devices_are_named_per_driver_and_signal() -> None:
    assert od_calibration_device("photodiodes", "90") == "od90"
    assert od_calibration_device("turbidvision", "reflectance") == "od_turbidvision_reflectance"


# --- the shared OD job with an external device


def test_external_source_uses_native_job_without_photodiodes(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor.background_jobs.od_reading import ADCReader

    monkeypatch.setattr(
        ADCReader, "__init__", MagicMock(side_effect=AssertionError("ADC must not be initialized"))
    )
    with start_od_reading(unit=get_unit_name(), experiment="test_source", interval=None) as job:
        assert isinstance(job, ExternalODReader)
        assert job.job_name == "od_reading"
        assert job.source == "test_probe"
        assert job.acquisition == "continuous"
        assert "first_od_obs_time" not in job.published_settings
        reading = job.record()
        assert reading is not None
        decoded = decode(encode(reading), type=structs.ODReadings)
        assert decoded.ods["1"].od == 7.4e-7
        assert decoded.ods["1"].angle == "0"
        assert job.raw_od1 is None
        job.set_state(job.SLEEPING)
        external_source.pause.assert_called_once()
        assert job.record() is None
        job.set_state(job.READY)
        assert external_source.start.call_count == 2
    external_source.close.assert_called_once()


def test_source_start_failure_closes_driver(external_source: MagicMock) -> None:
    external_source.start.side_effect = OSError("start failed")
    with pytest.raises(OSError, match="start failed"):
        start_od_reading(unit=get_unit_name(), experiment="test_start_fail", interval=None)
    external_source.close.assert_called_once()


def test_no_new_sample_publishes_nothing(external_source: MagicMock) -> None:
    with start_od_reading(unit=get_unit_name(), experiment="test_samples", interval=None) as job:
        external_source.read.return_value = None
        assert job.record() is None
        assert job.ods is None


def test_multiple_outputs_publish_on_their_own_channels_and_geometry(external_source: MagicMock) -> None:
    external_source.outputs = {"1": REFLECTANCE, "2": FLUORESCENCE, "3": DENSITY}
    external_source.read.return_value = _readings(0.25, 1200.0, 0.8)
    with start_od_reading(unit=get_unit_name(), experiment="multi_output", interval=None) as job:
        batch = job.record()
        assert batch is not None
        assert {
            channel: (reading.od, reading.angle, reading.calibrated) for channel, reading in batch.ods.items()
        } == {
            "1": (0.25, "0", 0),
            "2": (1200.0, "90", 0),
            "3": (0.8, "0", 1),
        }
        assert job.od2 is not None and job.od2.angle == "90"


def test_undeclared_channel_is_rejected(external_source: MagicMock) -> None:
    external_source.read.return_value = _readings(0.25, 0.3)
    with start_od_reading(unit=get_unit_name(), experiment="undeclared_channel", interval=None) as job:
        with pytest.raises(ValueError, match="channel 2, which is not one of its outputs"):
            job.record()


def test_signal_names_must_be_valid_storage_names(external_source: MagicMock) -> None:
    external_source.outputs = {"1": ODSignal(name="bad/name", angle="0", scale="x")}
    with pytest.raises(ValueError, match="signal name"):
        start_od_reading(unit=get_unit_name(), experiment="bad_signal_name", interval=None)
    external_source.start.assert_not_called()
    external_source.close.assert_called_once()


def test_device_preserves_acquisition_time(external_source: MagicMock) -> None:
    timestamp = current_utc_datetime()
    external_source.read.return_value = _readings(0.5, timestamp=timestamp)
    with start_od_reading(unit=get_unit_name(), experiment="device_outputs", interval=None) as job:
        batch = job.record()
        assert batch.timestamp == timestamp
        assert job.od1.timestamp == timestamp


# --- calibrations applied by the job


def test_active_signal_calibration_converts_signal_and_keeps_raw(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    external_source.outputs = {"1": REFLECTANCE, "2": FLUORESCENCE}
    requested = _activate(monkeypatch, {"od_test_probe_reflectance": _calibration()})
    external_source.read.return_value = _readings(0.25, 1200.0)
    with start_od_reading(unit=get_unit_name(), experiment="external_calibrated", interval=None) as job:
        batch = job.record()
        assert batch is not None
        assert batch.ods["1"].od == pytest.approx(1.0)
        assert batch.ods["1"].calibrated == 1
        assert job.raw_od1 is not None
        assert (job.raw_od1.od, job.raw_od1.calibrated, job.raw_od1.angle) == (0.25, 0, "0")
        # The uncalibrated output is published as is, without a raw copy.
        assert (batch.ods["2"].od, batch.ods["2"].calibrated) == (1200.0, 0)
        assert job.raw_od2 is None
        # Signals beyond the standards clamp to the calibrated range.
        external_source.read.return_value = _readings(0.9, 1200.0)
        assert job.record().ods["1"].od == 2.0
    # One lookup per signal, keyed by driver and signal name.
    assert requested == ["od_test_probe_reflectance", "od_test_probe_fluorescence"]


def test_uncalibrated_start_publishes_device_values(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _activate(monkeypatch, {"od_test_probe_reflectance": _calibration()})
    external_source.read.return_value = _readings(0.25)
    with start_external_od_reading(
        unit=get_unit_name(), experiment="external_raw", interval=None, calibration=False
    ) as job:
        batch = job.record()
        assert (batch.ods["1"].od, batch.ods["1"].calibrated) == (0.25, 0)


def test_scale_mismatch_fails_before_acquisition_starts(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    rescaled = ODSignal(name="reflectance", angle="0", scale="reflectance ratio, v2")
    _activate(monkeypatch, {"od_test_probe_reflectance": _calibration(rescaled)})
    with pytest.raises(exc.CalibrationError, match="was fit on reflectance ratio, v2.*reflectance ratio, v1"):
        start_od_reading(unit=get_unit_name(), experiment="external_rescaled", interval=None)
    external_source.start.assert_not_called()
    external_source.close.assert_called_once()


def test_scale_change_while_running_stops_publishing_calibrated_values(external_source: MagicMock) -> None:
    external_source.read.return_value = _readings(0.25)
    with start_external_od_reading(
        unit=get_unit_name(), experiment="external_scale_change", interval=None, calibration=_calibration()
    ) as job:
        assert job.record() is not None
        external_source.outputs = {
            "1": ODSignal(name="reflectance", angle="0", scale="reflectance ratio, v2")
        }
        with pytest.raises(exc.CalibrationError, match="now reads on reflectance ratio, v2"):
            job.record()
        assert job.ods is None
        assert job.od1 is None
        assert job.raw_od1 is not None and job.raw_od1.od == 0.25


def test_calibration_is_never_applied_to_a_device_calibrated_output(external_source: MagicMock) -> None:
    external_source.outputs = {"1": DENSITY}
    with pytest.raises(exc.CalibrationError, match="already calibrates that output"):
        start_external_od_reading(
            unit=get_unit_name(),
            experiment="external_double_calibration",
            interval=None,
            calibration=_calibration(DENSITY),
        )
    external_source.start.assert_not_called()


@pytest.mark.parametrize(
    "calibration, match",
    [
        (_calibration(driver="other_probe"), "fit on the `other_probe` OD device"),
        (
            _calibration(FLUORESCENCE),
            "`fluorescence` signal, which the `test_probe` OD device is not producing",
        ),
    ],
)
def test_calibration_for_another_driver_or_signal_is_rejected(
    external_source: MagicMock, calibration: structs.ExternalODCalibration, match: str
) -> None:
    with pytest.raises(exc.CalibrationError, match=match):
        start_external_od_reading(
            unit=get_unit_name(), experiment="external_wrong_target", interval=None, calibration=calibration
        )


def test_photodiode_calibration_on_external_device_is_rejected(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    photodiode_calibration = structs.OD600Calibration(
        calibration_name="photodiode",
        calibrated_on_pioreactor_unit=get_unit_name(),
        created_at=current_utc_datetime(),
        curve_data_=structs.PolyFitCoefficients(coefficients=[0.2, 0.05]),
        recorded_data={"x": [0.0, 1.0], "y": [0.05, 0.25]},
        ir_led_intensity=70.0,
        angle="90",
        pd_channel="2",
    )
    _activate(monkeypatch, {"od_test_probe_reflectance": photodiode_calibration})
    with pytest.raises(exc.CalibrationError, match="wrong type"):
        start_od_reading(unit=get_unit_name(), experiment="external_wrong_type", interval=None)
    external_source.start.assert_not_called()


# --- the rest of the system with an external device


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
    (model / "od.yaml").write_text(
        "driver: test_probe\noptions:\n  bus: 1\n  address: 0x69\n", encoding="utf-8"
    )
    assert hardware.get_required_i2c_addresses_for_model("pioreactor_40ml", "1.5") == {44}


def test_unknown_source_never_falls_back_to_adc(monkeypatch: pytest.MonkeyPatch) -> None:
    from pioreactor.od_devices import create_od_device
    from pioreactor import plugin_management

    monkeypatch.setattr(plugin_management, "get_plugins", lambda: {})
    with pytest.raises(Exception, match="not installed"):
        create_od_device(hardware.ODHardwareConfig(driver="missing"), MagicMock())


@pytest.mark.parametrize("angle", ["0", "90", "180"])
def test_sensor_geometry_round_trips_through_existing_od_table(angle: pt.ObservationAngle) -> None:
    import sqlite3
    from pioreactor.background_jobs.leader.mqtt_to_db_streaming import parse_od
    from pioreactor.background_jobs.leader.mqtt_to_db_streaming import parse_raw_od

    reading = structs.ODReading(
        timestamp=current_utc_datetime(),
        od=7.45279e-7,
        channel="1",
        angle=angle,
        calibrated=0,
    )
    connection = sqlite3.connect(":memory:")
    schema = (Path(__file__).parents[2] / "packaging/shared-assets/sql/create_tables.sql").read_text(
        encoding="utf-8"
    )
    connection.executescript(schema)
    for table, parse, topic in [
        ("od_readings", parse_od, "od1"),
        ("raw_od_readings", parse_raw_od, "raw_od1"),
    ]:
        row = parse(f"pioreactor/unit/experiment/od_reading/{topic}", encode(reading))
        assert row["angle"] == int(angle)
        columns = ",".join(row)
        connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in row)})", tuple(row.values())
        )
        stored = connection.execute(f"SELECT angle,od_reading FROM {table}").fetchone()
        assert stored == (int(angle), 7.45279e-7)
    connection.close()


def test_raw_od_from_older_photodiode_workers_still_parses() -> None:
    from pioreactor.background_jobs.leader.mqtt_to_db_streaming import parse_raw_od

    legacy = {
        "timestamp": "2026-09-01T01:00:00Z",
        "od": 0.1,
        "channel": "2",
        "angle": "90",
        "ir_led_intensity": 70.0,
        "calibrated": 0,
    }
    row = parse_raw_od("pioreactor/unit/experiment/od_reading/raw_od2", encode(legacy))
    assert (row["od_reading"], row["channel"], row["angle"]) == (0.1, 2, 90)


@pytest.mark.parametrize("signal", [REFLECTANCE, DENSITY])
def test_external_geometry_survives_publication_and_averaging(
    external_source: MagicMock, signal: ODSignal
) -> None:
    from pioreactor.background_jobs.od_reading import average_over_od_readings

    external_source.outputs = {"1": signal}
    external_source.read.return_value = _readings(0.42)
    with start_od_reading(unit=get_unit_name(), experiment="sensor_geometry", interval=None) as job:
        reading = job.record()
        assert reading is not None
        decoded = decode(encode(reading), type=structs.ODReadings)
        assert decoded.ods["1"].angle == signal.angle
        assert decoded.ods["1"].calibrated == int(signal.calibrated)
        averaged = average_over_od_readings(decoded, decoded).ods["1"]
        assert averaged.angle == signal.angle
        assert averaged.calibrated == int(signal.calibrated)


def test_non_i2c_driver_receives_its_options(monkeypatch: pytest.MonkeyPatch) -> None:
    from pioreactor.od_devices import create_od_device

    options = {"port": "/dev/ttyUSB0", "baudrate": 115200}
    monkeypatch.setattr(
        hardware, "get_layered_mod_config", lambda mod: {"driver": "serial_test", "options": options}
    )
    factory = MagicMock()
    register_od_device("serial_test", factory)
    logger = MagicMock()
    selected = hardware.get_od_hardware_config()
    assert create_od_device(selected, logger) is factory.return_value
    factory.assert_called_once_with(options, logger)


@pytest.mark.parametrize("data", [{"driver": "test", "bus": 1}, {"driver": "test", "options": []}])
def test_od_config_rejects_invalid_outer_shape(monkeypatch: pytest.MonkeyPatch, data: dict) -> None:
    from msgspec import ValidationError

    monkeypatch.setattr(hardware, "get_layered_mod_config", lambda mod: data)
    with pytest.raises(ValidationError):
        hardware.get_od_hardware_config()


def test_self_tests_skip_photodiode_operations(external_source: MagicMock) -> None:
    from pioreactor.actions.self_test import get_builtin_self_tests

    names = {test.__name__ for test in get_builtin_self_tests()}
    assert "test_REF_is_in_correct_position" not in names
    assert "test_positive_correlation_between_rpm_and_stirring" in names


@pytest.mark.parametrize("signal", [REFLECTANCE, DENSITY])
def test_probe_mqtt_reaches_native_growth_model(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch, signal: ODSignal
) -> None:
    import math
    from datetime import timedelta
    from threading import Thread
    from pioreactor.config import config
    from pioreactor.config import temporary_config_changes
    from .utils import wait_for

    experiment = "test_probe_native_growth"
    external_source.outputs = {"1": signal}
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
                with start_od_reading(unit=get_unit_name(), experiment=experiment, interval=None) as job:
                    for index in range(10):
                        timestamp += timedelta(seconds=5)
                        base = 0.42 if signal.calibrated else 7.4e-7
                        external_source.read.return_value = _readings(
                            base * (1.001**index), timestamp=timestamp
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


@pytest.mark.parametrize("interval, expected_penalizer", [(None, 0.0), (5.0, 0.6)])
def test_configured_photodiode_start_loads_defaults(
    monkeypatch: pytest.MonkeyPatch, interval: float | None, expected_penalizer: float
) -> None:
    import pioreactor.background_jobs.od_reading as module
    from pioreactor.config import config
    from pioreactor.config import temporary_config_changes

    monkeypatch.setattr(hardware, "get_od_hardware_config", lambda: hardware.ODHardwareConfig())
    start = MagicMock()
    monkeypatch.setattr(module, "start_photodiode_od_reading", start)
    with temporary_config_changes(config, [("od_reading.config", "smoothing_penalizer", "3.0")]):
        result = start_od_reading(unit="test", experiment="configured", interval=interval)
    assert result is start.return_value
    assert start.call_args.args == (dict(config.items("od_config.photodiode_channel")),)
    assert start.call_args.kwargs["unit"] == "test"
    assert start.call_args.kwargs["experiment"] == "configured"
    assert start.call_args.kwargs["interval"] == interval
    assert start.call_args.kwargs["penalizer"] == expected_penalizer


def test_cli_probe_snapshot_uses_configured_hardware(
    external_source: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    from pioreactor.background_jobs.od_reading import click_od_reading

    click_od_reading.callback(fake_data=False, interval=None, ir_led_intensity=None, snapshot=True)
    assert decode(capsys.readouterr().out)["ods"]["1"]["calibrated"] == 0
    external_source.start.assert_called_once()
    external_source.close.assert_called_once()


@pytest.mark.parametrize("fake_data, intensity", [(True, None), (False, 50.0)])
def test_cli_rejects_photodiode_options_for_probe(
    external_source: MagicMock, fake_data: bool, intensity: float | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor.background_jobs.od_reading import click_od_reading

    from pioreactor.config import config

    # Probe installations need not have a photodiode channel section.
    original_items = config.items

    def items(section: str) -> list[tuple[str, str]]:
        if section == "od_config.photodiode_channel":
            raise AssertionError("Probe startup must not read photodiode channels")
        return original_items(section)

    monkeypatch.setattr(config, "items", items)
    with pytest.raises(exc.HardwareError, match="not supported"):
        click_od_reading.callback(
            fake_data=fake_data, interval=None, ir_led_intensity=intensity, snapshot=True
        )
    external_source.start.assert_not_called()


# --- calibrating an external device with OD600 standards


def _run_standards_session(
    external_source: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    readings: list[ODDeviceReadings],
    od600s: list[float],
) -> tuple[Any, list[dict[str, Any]]]:
    from pioreactor.calibrations.protocols import od_standards
    from pioreactor.calibrations.session_flow import advance_session
    from pioreactor.calibrations.session_flow import get_session_step

    monkeypatch.setattr(od_standards, "is_pio_job_running", lambda _jobs: [False, False])
    monkeypatch.setattr(od_standards, "list_of_calibrations_by_device", lambda _device: [])
    registry = od_standards._OD_STANDARDS_STEPS
    measurements = iter(readings)
    saved: list[dict[str, Any]] = []

    def execute(action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "od_standards_measure_external":
            external_source.read.return_value = next(measurements)
            return {"signals": od_standards._measure_external_standard(payload["rpm"], payload["experiment"])}
        assert action == "save_calibration"
        saved.append(payload)
        return {"path": f"/tmp/{payload['device']}.yaml"}

    assert od_standards.get_valid_od_devices_for_this_unit() == ["od_test_probe"]
    session = od_standards.start_standards_session("od_test_probe")
    # Starting a session needs no hardware: outputs are discovered by the first measurement.
    external_source.start.assert_not_called()

    session = advance_session(registry, session, {}, execute)
    session = advance_session(registry, session, {"calibration_name": "probe-standards"}, execute)
    assert session.step_id == "setup"
    session = advance_session(registry, session, {"rpm": 0, "sample_count": len(od600s)}, execute)
    session = advance_session(registry, session, {}, execute)
    session = advance_session(registry, session, {"od600_blank": od600s[0]}, execute)
    for od600 in od600s[1:]:
        session = advance_session(registry, session, {}, execute)
        step = get_session_step(registry, session, execute)
        assert step.metadata["table"]["columns"][:3] == ["Standard", "OD600", "Signal, reflectance"]
        session = advance_session(registry, session, {"od600_value": od600}, execute)
    assert session.step_id == "review_data"
    review = get_session_step(registry, session, execute)
    session = advance_session(registry, session, {"recorded_data": review.fields[0].default}, execute)
    return session, saved


def test_standards_protocol_calibrates_each_uncalibrated_output(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from msgspec import convert

    external_source.outputs = {"1": REFLECTANCE, "2": DENSITY, "3": FLUORESCENCE}
    od600s = [0.0, 0.5, 1.0, 2.0]
    # Blank first, then three standards: reflectance = 0.2 * OD600 + 0.05.
    readings = [_readings(0.05 + 0.2 * od, od, 100 + od) for od in od600s]
    session, saved = _run_standards_session(external_source, monkeypatch, readings, od600s)
    assert session.status == "complete"

    # The device-calibrated density output is never fit; each other output gets its own device.
    assert [payload["device"] for payload in saved] == [
        "od_test_probe_reflectance",
        "od_test_probe_fluorescence",
    ]
    calibration = convert(saved[0]["calibration"], type=structs.ExternalODCalibration)
    assert (calibration.driver, calibration.signal, calibration.signal_scale) == (
        "test_probe",
        "reflectance",
        REFLECTANCE.scale,
    )
    assert calibration.recorded_data == {"x": od600s, "y": pytest.approx([0.05, 0.15, 0.25, 0.45])}

    # The saved curve turns the signal back into the standards' OD600.
    external_source.read.return_value = _readings(0.25, 1.0, 101.0)
    with start_external_od_reading(
        unit=get_unit_name(), experiment="external_round_trip", interval=None, calibration=calibration
    ) as job:
        batch = job.record()
        assert batch.ods["1"].od == pytest.approx(1.0, abs=0.02)
        assert batch.ods["1"].calibrated == 1
        assert batch.ods["2"].calibrated == 1  # the device's own calibration
        assert batch.ods["3"].calibrated == 0


def test_standards_session_rejects_outputs_that_change_mid_calibration(
    external_source: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor.calibrations.protocols import od_standards
    from pioreactor.calibrations.session_flow import SessionContext
    from pioreactor.calibrations.session_flow import SessionInputs

    session = od_standards.start_standards_session("od_test_probe")
    ctx = SessionContext(session, "cli", SessionInputs({}), [])
    external_source.read.return_value = _readings(0.05)
    assert od_standards._measure_standard_for_session(ctx, 0, {}) == {"reflectance": pytest.approx(0.05)}
    external_source.outputs = {"1": ODSignal(name="reflectance", angle="0", scale="reflectance ratio, v2")}
    with pytest.raises(ValueError, match="outputs changed during this calibration"):
        od_standards._measure_standard_for_session(ctx, 0, {})


def test_standards_measurement_needs_an_uncalibrated_output(external_source: MagicMock) -> None:
    from pioreactor.calibrations.protocols import od_standards

    external_source.outputs = {"1": DENSITY}
    external_source.read.return_value = _readings(0.25)
    with pytest.raises(ValueError, match="calibrates all of its outputs itself"):
        od_standards._measure_external_standard(0, "external_device_calibrated")
    external_source.close.assert_called_once()


@pytest.mark.parametrize(
    "active, expected_signal",
    [({"od_test_probe_reflectance": "active"}, "od"), ({}, "normalized_od")],
)
def test_turbidostat_auto_follows_external_device_calibration(
    external_source: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    active: dict[str, str],
    expected_signal: str,
) -> None:
    from pioreactor.automations.dosing.turbidostat import Turbidostat

    monkeypatch.setattr(
        "pioreactor.automations.dosing.turbidostat.list_devices",
        lambda: ["od90", "od_other_probe_reflectance", "od_test_probe_reflectance", "media_pump"],
    )
    requested: list[str] = []

    def load_active_calibration(device: str) -> str | None:
        requested.append(device)
        return active.get(device)

    # Signal selection is independent of pump readiness.
    monkeypatch.setattr(
        "pioreactor.automations.dosing.turbidostat.check_pump_calibrations_and_pwm_channels_are_configured",
        lambda pump_devices: None,
    )
    # A fused estimator left over from the photodiodes must not capture the probe's unit.
    monkeypatch.setattr(
        "pioreactor.automations.dosing.turbidostat.load_active_estimator", lambda device: object()
    )
    monkeypatch.setattr(
        "pioreactor.automations.dosing.turbidostat.load_active_calibration", load_active_calibration
    )
    with Turbidostat(
        target_biomass=0.5,
        duration=60,
        exchange_volume_ml=0.25,
        unit=get_unit_name(),
        experiment=f"turbidostat_external_{expected_signal}",
        skip_first_run=True,
    ) as algo:
        assert algo.resolved_biomass_signal == expected_signal
        assert algo._od_channel == "1"
    # Only this driver's signals are considered.
    assert requested == ["od_test_probe_reflectance"]
