# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import cast

import pytest
from pioreactor.calibrations.protocols import pump_duration_based
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionInputs
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.types import PumpCalibrationDevices


def _make_context(data: dict[str, object] | None = None) -> SessionContext:
    session = CalibrationSession(
        session_id="session-1",
        protocol_name="pump",
        target_device="media_pump",
        status="in_progress",
        step_id="intro",
        data=data or {},
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    return SessionContext(session=session, mode="cli", inputs=SessionInputs(None), collected_calibrations=[])


def test_get_execute_pump_for_device_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown pump device"):
        pump_duration_based._get_execute_pump_for_device(cast(PumpCalibrationDevices, "unknown"))


def test_build_duration_chart_metadata_uses_min_length() -> None:
    ctx = _make_context({"durations_to_test": [1.0, 2.0, 3.0], "results": [0.5]})

    metadata = pump_duration_based._build_duration_chart_metadata(ctx)
    assert metadata is not None
    series = cast(list[dict[str, object]], metadata["series"])
    points = cast(list[dict[str, float]], series[0]["points"])
    assert points == [{"x": 1.0, "y": 0.5}]
