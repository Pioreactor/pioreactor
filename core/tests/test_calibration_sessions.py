# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Generator

import pytest
from pioreactor.calibrations.session_flow import fields
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionEngine
from pioreactor.calibrations.session_flow import SessionInputs
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import delete_calibration_session
from pioreactor.calibrations.structured_session import load_calibration_session
from pioreactor.calibrations.structured_session import save_calibration_session
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.utils import local_persistent_storage


@pytest.fixture(autouse=True)
def clear_calibration_sessions() -> Generator[None, None, None]:
    with local_persistent_storage("calibration_sessions") as store:
        for key in list(store.iterkeys()):
            del store[key]
    yield
    with local_persistent_storage("calibration_sessions") as store:
        for key in list(store.iterkeys()):
            del store[key]


def _build_session(session_id: str = "session-1") -> CalibrationSession:
    return CalibrationSession(
        session_id=session_id,
        protocol_name="test_protocol",
        target_device="test_device",
        status="in_progress",
        step_id="start",
        data={},
        created_at=utc_iso_timestamp(),
        updated_at=utc_iso_timestamp(),
        result=None,
        error=None,
    )


def test_save_load_abort_delete_session() -> None:
    session = _build_session()
    save_calibration_session(session)

    loaded = load_calibration_session(session.session_id)
    assert loaded is not None
    assert loaded.session_id == session.session_id
    assert loaded.protocol_name == session.protocol_name
    assert loaded.status == "in_progress"

    previous_updated_at = loaded.updated_at
    session.status = "aborted"
    session.error = "Stop."
    session.updated_at = utc_iso_timestamp()
    save_calibration_session(session)
    aborted = load_calibration_session(session.session_id)
    assert aborted is not None
    assert aborted.status == "aborted"
    assert aborted.error == "Stop."
    assert aborted.updated_at != previous_updated_at

    delete_calibration_session(session.session_id)
    assert load_calibration_session(session.session_id) is None


def test_session_inputs_parsing() -> None:
    inputs = SessionInputs(
        {
            "name": "  demo ",
            "rpm": "250.5",
            "count": "3",
            "mode": "fast",
            "values": "1.1, 2.2,3.3",
        }
    )

    assert inputs.str("name") == "demo"
    assert inputs.float("rpm", minimum=100.0) == pytest.approx(250.5)
    assert inputs.int("count", minimum=1) == 3
    assert inputs.choice("mode", ["slow", "fast"]) == "fast"
    assert inputs.float_list("values") == [1.1, 2.2, 3.3]

    with pytest.raises(ValueError):
        inputs.float("rpm", maximum=10.0)
    with pytest.raises(ValueError):
        inputs.choice("mode", ["slow"])


def test_session_engine_advances_and_completes() -> None:
    session = _build_session()

    def flow(ctx: SessionContext) -> CalibrationStep:
        if ctx.session.status != "in_progress":
            if ctx.session.result is not None:
                return steps.result(ctx.session.result)
            return steps.info("Calibration ended", "This calibration session has ended.")
        if ctx.step == "start":
            ctx.step = "name"
            return steps.form("Name", "Provide a name.", [fields.str("name")])
        if ctx.step == "name":
            ctx.data["name"] = ctx.inputs.str("name")
            ctx.complete({"name": ctx.data["name"]})
            return steps.result(ctx.session.result or {})
        return steps.info("Unknown step", "This step is not recognized.")

    engine = SessionEngine(flow=flow, session=session, mode="ui")
    step = engine.get_step()
    assert step.step_type == "form"

    step = engine.advance({"name": "Example"})
    assert step.step_type == "result"
    assert engine.session.status == "complete"
    assert engine.session.result == {"name": "Example"}

    engine.save()
    loaded = load_calibration_session(session.session_id)
    assert loaded is not None
    assert loaded.status == "complete"


def test_read_voltage_requires_executor_in_ui() -> None:
    session = _build_session()

    def executor(action: str, payload: dict[str, object]) -> dict[str, object]:
        assert action == "read_voltage"
        return {"voltage": "3.3"}

    def flow(ctx: SessionContext) -> CalibrationStep:
        return steps.info("", "")

    engine = SessionEngine(flow=flow, session=session, mode="ui", executor=executor)
    assert engine.ctx.read_voltage() == pytest.approx(3.3)


def test_read_voltage_not_available_in_cli() -> None:
    session = _build_session()

    def flow(ctx: SessionContext) -> CalibrationStep:
        return steps.info("", "")

    engine = SessionEngine(flow=flow, session=session, mode="cli")
    with pytest.raises(ValueError):
        engine.ctx.read_voltage()
