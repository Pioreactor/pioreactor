# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from datetime import timezone

import pytest
from pioreactor.calibrations.protocols import stirring_dc_based
from pioreactor.config import config
from pioreactor.config import temporary_config_change


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
