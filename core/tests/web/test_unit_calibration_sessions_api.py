# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionStep
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import save_calibration_session
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.web import unit_calibration_sessions_api as api


class IntroStep(SessionStep):
    step_id = "intro"

    def render(self, ctx: SessionContext):
        return steps.form("Intro", "Provide input.", [])

    def advance(self, ctx: SessionContext):
        return NextStep()


class NextStep(SessionStep):
    step_id = "next"

    def render(self, ctx: SessionContext):
        return steps.info("Next", "Advanced.")


class DummyProtocol:
    protocol_name = "dummy"
    target_device = "device"
    step_registry = {IntroStep.step_id: IntroStep, NextStep.step_id: NextStep}

    @staticmethod
    def start_session(target_device: str) -> CalibrationSession:
        now = utc_iso_timestamp()
        return CalibrationSession(
            session_id="session-1",
            protocol_name=DummyProtocol.protocol_name,
            target_device=target_device,
            status="in_progress",
            step_id=IntroStep.step_id,
            data={},
            created_at=now,
            updated_at=now,
        )


def _patch_protocols(monkeypatch) -> None:
    monkeypatch.setattr(api, "get_protocol", lambda target_device, protocol_name: DummyProtocol)
    monkeypatch.setattr(api, "get_protocol_for_session", lambda session: DummyProtocol)


def test_start_calibration_session_missing_payload(client) -> None:
    response = client.post("/unit_api/calibrations/sessions", json={})
    assert response.status_code == 400


def test_start_calibration_session_success(client, monkeypatch) -> None:
    _patch_protocols(monkeypatch)

    response = client.post(
        "/unit_api/calibrations/sessions",
        json={"protocol_name": DummyProtocol.protocol_name, "target_device": "device"},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["session"]["protocol_name"] == DummyProtocol.protocol_name
    assert payload["step"]["step_id"] == "intro"


def test_get_calibration_session_not_found(client) -> None:
    response = client.get("/unit_api/calibrations/sessions/unknown")
    assert response.status_code == 404


def test_abort_calibration_session_updates_status(client, monkeypatch) -> None:
    _patch_protocols(monkeypatch)

    session = DummyProtocol.start_session("device")
    save_calibration_session(session)

    response = client.post(f"/unit_api/calibrations/sessions/{session.session_id}/abort")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["session"]["status"] == "aborted"
    assert payload["session"]["error"] == "Calibration aborted by user."


def test_advance_calibration_session_validates_inputs(client, monkeypatch) -> None:
    _patch_protocols(monkeypatch)

    session = DummyProtocol.start_session("device")
    save_calibration_session(session)

    response = client.post(
        f"/unit_api/calibrations/sessions/{session.session_id}/inputs",
        json={"inputs": ["bad"]},
    )
    assert response.status_code == 400


def test_advance_calibration_session_advances_step(client, monkeypatch) -> None:
    _patch_protocols(monkeypatch)

    session = DummyProtocol.start_session("device")
    save_calibration_session(session)

    response = client.post(
        f"/unit_api/calibrations/sessions/{session.session_id}/inputs",
        json={"inputs": {}},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["session"]["step_id"] == "next"
    assert payload["step"]["step_id"] == "next"
