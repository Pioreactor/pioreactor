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


class FloatListStep(SessionStep):
    step_id = "float-list"

    def render(self, ctx: SessionContext):
        from pioreactor.calibrations.session_flow import fields

        return steps.form("Float list", "Provide values.", [fields.float_list("values")])

    def advance(self, ctx: SessionContext):
        ctx.inputs.float_list("values")
        return NextStep()


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

    @classmethod
    def on_session_abort(
        cls,
        session: CalibrationSession,
        executor=None,
    ) -> None:
        return None


class FloatListProtocol(DummyProtocol):
    protocol_name = "float_list"
    step_registry = {FloatListStep.step_id: FloatListStep, NextStep.step_id: NextStep}

    @staticmethod
    def start_session(target_device: str) -> CalibrationSession:
        now = utc_iso_timestamp()
        return CalibrationSession(
            session_id="session-float-list",
            protocol_name=FloatListProtocol.protocol_name,
            target_device=target_device,
            status="in_progress",
            step_id=FloatListStep.step_id,
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


def test_abort_calibration_session_runs_cleanup_hook(client, monkeypatch) -> None:
    class CleanupProtocol(DummyProtocol):
        cleanup_calls: list[tuple[str, bool]] = []

        @classmethod
        def on_session_abort(cls, session: CalibrationSession, executor=None) -> None:
            cls.cleanup_calls.append((session.session_id, executor is not None))

    monkeypatch.setattr(api, "get_protocol", lambda target_device, protocol_name: CleanupProtocol)
    monkeypatch.setattr(api, "get_protocol_for_session", lambda session: CleanupProtocol)

    session = CleanupProtocol.start_session("device")
    save_calibration_session(session)

    response = client.post(f"/unit_api/calibrations/sessions/{session.session_id}/abort")
    assert response.status_code == 200
    assert CleanupProtocol.cleanup_calls == [(session.session_id, True)]


def test_abort_calibration_session_reports_cleanup_error(client, monkeypatch) -> None:
    class FailingCleanupProtocol(DummyProtocol):
        @classmethod
        def on_session_abort(cls, session: CalibrationSession, executor=None) -> None:
            raise RuntimeError("cleanup exploded")

    monkeypatch.setattr(api, "get_protocol", lambda target_device, protocol_name: FailingCleanupProtocol)
    monkeypatch.setattr(api, "get_protocol_for_session", lambda session: FailingCleanupProtocol)

    session = FailingCleanupProtocol.start_session("device")
    save_calibration_session(session)

    response = client.post(f"/unit_api/calibrations/sessions/{session.session_id}/abort")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["session"]["status"] == "aborted"
    assert "Cleanup failed: cleanup exploded" in payload["session"]["error"]


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


def test_advance_calibration_session_invalid_float_list_returns_400(client, monkeypatch) -> None:
    monkeypatch.setattr(api, "get_protocol", lambda target_device, protocol_name: FloatListProtocol)
    monkeypatch.setattr(api, "get_protocol_for_session", lambda session: FloatListProtocol)

    session = FloatListProtocol.start_session("device")
    save_calibration_session(session)

    response = client.post(
        f"/unit_api/calibrations/sessions/{session.session_id}/inputs",
        json={"inputs": {"values": [1, None]}},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert "Invalid 'values', expected list of numbers." in payload["error"]
