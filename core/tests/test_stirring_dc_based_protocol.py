# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from datetime import timezone
from unittest.mock import MagicMock

import pytest
from pioreactor.calibrations.protocols import stirring_dc_based
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionInputs
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


def test_run_calibration_has_specific_primary_action_label() -> None:
    ctx = SessionContext(
        session=_dummy_session(),
        mode="ui",
        inputs=SessionInputs(None),
        collected_calibrations=[],
    )

    assert (
        stirring_dc_based.RunCalibration().render(ctx).metadata["primary_action_label"] == "Run calibration"
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


@pytest.fixture
def stirring_measurement_hardware(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    lifecycle = MagicMock()
    lifecycle.__enter__.return_value = lifecycle
    lifecycle.exit_event.wait.return_value = False
    rpm_calculator = MagicMock()
    rpm_calculator.__enter__.return_value = rpm_calculator
    stirrer = MagicMock()
    stirrer.__enter__.return_value = stirrer

    monkeypatch.setattr(stirring_dc_based, "managed_lifecycle", lambda *args, **kwargs: lifecycle)
    monkeypatch.setattr(stirring_dc_based, "is_pio_job_running", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(stirring_dc_based, "is_testing_env", lambda: False)
    monkeypatch.setattr(stirring_dc_based.stirring, "RpmFromFrequency", lambda: rpm_calculator)
    monkeypatch.setattr(stirring_dc_based.stirring, "Stirrer", lambda *args, **kwargs: stirrer)
    return lifecycle, rpm_calculator, stirrer


def test_collect_stirring_measurements_interrupts_on_exit_event(
    stirring_measurement_hardware: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    lifecycle, rpm_calculator, stirrer = stirring_measurement_hardware
    lifecycle.exit_event.wait.return_value = True

    with pytest.raises(InterruptedError, match="Stirring calibration aborted"):
        stirring_dc_based.collect_stirring_measurements(min_dc=10.0, max_dc=20.0)

    rpm_calculator.estimate.assert_not_called()
    rpm_calculator.__exit__.assert_called_once()
    stirrer.__exit__.assert_called_once()
    lifecycle.__exit__.assert_called_once()


def test_collect_stirring_measurements_reports_no_positive_rpm(
    stirring_measurement_hardware: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    lifecycle, rpm_calculator, stirrer = stirring_measurement_hardware
    rpm_calculator.estimate.return_value = 0.0

    with pytest.raises(ValueError) as exc_info:
        stirring_dc_based.collect_stirring_measurements(min_dc=10.0, max_dc=20.0)

    assert str(exc_info.value) == (
        "No positive RPM readings were detected between 10% and 20% duty cycle. "
        "Check that the stirring motor turns and the heating PCB is connected."
    )
    assert rpm_calculator.estimate.call_count == 15
    rpm_calculator.__exit__.assert_called_once()
    stirrer.__exit__.assert_called_once()
    lifecycle.__exit__.assert_called_once()


def test_collect_stirring_measurements_keeps_positive_rpm_pairs(
    stirring_measurement_hardware: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, rpm_calculator, _ = stirring_measurement_hardware
    rpm_calculator.estimate.side_effect = [0.0, 100.0, 200.0, 0.0, 300.0] * 3

    dcs, rpms = stirring_dc_based.collect_stirring_measurements(min_dc=10.0, max_dc=20.0)

    assert dcs == [17.5, 15.0, 10.0, 12.5, 15.0, 20.0, 17.5, 15.0, 10.0]
    assert rpms == [100.0, 200.0, 300.0] * 3
