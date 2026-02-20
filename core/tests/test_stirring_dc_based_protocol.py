# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from datetime import timezone
from threading import Event

import pytest
from pioreactor.calibrations.protocols import stirring_dc_based
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.whoami import get_testing_experiment_name


def test_resolve_dc_bounds_uses_config_defaults() -> None:
    with temporary_config_change(config, "stirring.config", "initial_duty_cycle", "30"):
        min_dc, max_dc = stirring_dc_based._resolve_dc_bounds(None, None)

    assert min_dc == pytest.approx(19.8)
    assert max_dc == pytest.approx(39.9)


def test_resolve_dc_bounds_requires_both_values() -> None:
    with pytest.raises(ValueError, match="min_dc and max_dc must both be set"):
        stirring_dc_based._resolve_dc_bounds(min_dc=10.0, max_dc=None)


def test_resolve_dc_bounds_returns_provided_values() -> None:
    min_dc, max_dc = stirring_dc_based._resolve_dc_bounds(min_dc=10.0, max_dc=80.0)
    assert min_dc == 10.0
    assert max_dc == 80.0


def test_build_stirring_calibration_from_measurements(monkeypatch) -> None:
    fixed_now = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)

    monkeypatch.setattr(stirring_dc_based, "current_utc_datetime", lambda: fixed_now)

    calibration = stirring_dc_based._build_stirring_calibration_from_measurements(
        dcs=[10.0, 20.0, 30.0],
        rpms=[100.0, 200.0, 300.0],
        voltage=3.3,
        unit="unit1",
    )

    assert calibration.calibrated_on_pioreactor_unit == "unit1"
    assert calibration.voltage == 3.3
    assert calibration.recorded_data == {"x": [10.0, 20.0, 30.0], "y": [100.0, 200.0, 300.0]}
    assert calibration.pwm_hz == config.getfloat("stirring.config", "pwm_hz")
    assert calibration.calibration_name == "stirring-calibration-2026-01-02_03-04"


def _dummy_session() -> CalibrationSession:
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id="session-stir-1",
        protocol_name=stirring_dc_based.DCBasedStirringProtocol.protocol_name,
        target_device="stirring",
        status="in_progress",
        step_id="intro",
        data={},
        created_at=now,
        updated_at=now,
    )


def test_on_session_abort_requests_stirring_job_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bytes, int]] = []

    def fake_publish(topic: str, message: bytes, qos: int) -> None:
        calls.append((topic, message, qos))

    monkeypatch.setattr(stirring_dc_based, "publish", fake_publish)
    stirring_dc_based.DCBasedStirringProtocol.on_session_abort(_dummy_session())

    assert calls == [
        (
            f"pioreactor/{stirring_dc_based.get_unit_name()}/{get_testing_experiment_name()}/stirring_calibration/$state/set",
            b"disconnected",
            1,
        ),
        (
            f"pioreactor/{stirring_dc_based.get_unit_name()}/{get_testing_experiment_name()}/stirring/$state/set",
            b"disconnected",
            1,
        ),
    ]


def test_on_session_abort_aggregates_stirring_cleanup_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_publish(topic: str, message: bytes, qos: int) -> None:
        job_name = topic.split("/")[-3]
        raise RuntimeError(f"failed {job_name}")

    monkeypatch.setattr(stirring_dc_based, "publish", failing_publish)
    with pytest.raises(RuntimeError, match="failed stirring_calibration"):
        stirring_dc_based.DCBasedStirringProtocol.on_session_abort(_dummy_session())


def test_collect_stirring_measurements_interrupts_on_exit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyLifecycle:
        def __init__(self) -> None:
            self.exit_event = Event()
            self.exit_event.set()
            self.mqtt_client = type("MQTT", (), {"publish": lambda *args, **kwargs: None})()

        def __enter__(self) -> "DummyLifecycle":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return

    class DummyRpmCalculator:
        def setup(self) -> None:
            return

        def estimate(self, seconds_to_observe: float) -> float:
            return 0.0

        def __enter__(self) -> "DummyRpmCalculator":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return

    class DummyStirrer:
        def __init__(self, *args, **kwargs) -> None:
            self.duty_cycle = 0.0

        def start_stirring(self) -> None:
            return

        def set_duty_cycle(self, dc: float) -> None:
            self.duty_cycle = dc

        def __enter__(self) -> "DummyStirrer":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return

    monkeypatch.setattr(stirring_dc_based, "managed_lifecycle", lambda *args, **kwargs: DummyLifecycle())
    monkeypatch.setattr(stirring_dc_based, "is_pio_job_running", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(stirring_dc_based.stirring, "RpmFromFrequency", DummyRpmCalculator)
    monkeypatch.setattr(stirring_dc_based.stirring, "Stirrer", DummyStirrer)
    monkeypatch.setattr(stirring_dc_based, "linspace", lambda start, end, n: [start])

    with pytest.raises(InterruptedError, match="Stirring calibration aborted"):
        stirring_dc_based.collect_stirring_measurements(min_dc=10.0, max_dc=20.0)
