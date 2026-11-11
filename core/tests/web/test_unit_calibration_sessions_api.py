# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import Mock

import pytest
from flask.testing import FlaskClient
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionStep
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import save_calibration_session
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.utils.job_manager import JobManager
from pioreactor.web import unit_calibration_sessions_api as api
from pioreactor.web.config import huey

huey.immediate = True


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


def _advance(client, session_id: str, inputs) -> dict:
    """Submit inputs and return the finished task's payload."""
    response = client.post(f"/unit_api/calibrations/sessions/{session_id}/inputs", json={"inputs": inputs})
    assert response.status_code == 202
    task = client.get(response.get_json()["result_url_path"])
    assert task.status_code == 200
    return task.get_json()


def _use_protocol(monkeypatch, protocol) -> None:
    monkeypatch.setattr(api, "get_protocol", lambda target_device, protocol_name: protocol)
    monkeypatch.setattr(api, "get_protocol_for_session", lambda session: protocol)
    # The advance task looks protocols up through the registry.
    monkeypatch.setattr("pioreactor.calibrations.registry.get_protocol_for_session", lambda session: protocol)


def _patch_protocols(monkeypatch) -> None:
    _use_protocol(monkeypatch, DummyProtocol)


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


def test_start_pump_session_reports_conflicts_without_saving(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_session = Mock()
    monkeypatch.setattr(api, "save_calibration_session", save_session)
    with JobManager() as job_manager:
        for job_name in ["dosing_automation", "remove_waste"]:
            job_manager.register_and_set_running(
                unit="unit1",
                experiment="experiment",
                job_name=job_name,
                job_source="test",
                pid=12345,
                leader="leader",
                is_long_running_job=False,
            )

    response = client.post(
        "/unit_api/calibrations/sessions",
        json={"protocol_name": "duration_based", "target_device": "media_pump"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == (
        "Stop these jobs before starting pump calibration: dosing_automation, remove_waste."
    )
    save_session.assert_not_called()


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
    assert response.status_code == 500
    payload = response.get_json()
    assert "Cleanup failed: cleanup exploded" in payload["error"]
    stored = client.get(f"/unit_api/calibrations/sessions/{session.session_id}").get_json()
    assert stored["session"]["status"] == "aborted"


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

    task = _advance(client, session.session_id, {})
    assert task["status"] == "succeeded"
    assert task["result"]["session"]["step_id"] == "next"
    assert task["result"]["step"]["step_id"] == "next"

    stored = client.get(f"/unit_api/calibrations/sessions/{session.session_id}").get_json()
    assert stored["step"]["step_id"] == "next"


def test_advance_calibration_session_invalid_float_list_fails_the_task(client, monkeypatch) -> None:
    _use_protocol(monkeypatch, FloatListProtocol)

    session = FloatListProtocol.start_session("device")
    save_calibration_session(session)

    task = _advance(client, session.session_id, {"values": [1, None]})

    assert task["status"] == "failed"
    assert "Invalid 'values', expected list of numbers." in task["error"]


class AbortedDuringStep(SessionStep):
    step_id = "intro"

    def render(self, ctx: SessionContext):
        return steps.action("Slow", "Someone aborts while this runs.")

    def advance(self, ctx: SessionContext):
        aborted = DummyProtocol.start_session("device")
        aborted.status = "aborted"
        save_calibration_session(aborted)
        return NextStep()


class AbortedDuringStepProtocol(DummyProtocol):
    step_registry = {AbortedDuringStep.step_id: AbortedDuringStep, NextStep.step_id: NextStep}


def test_abort_while_a_step_runs_is_kept(client, monkeypatch) -> None:
    _use_protocol(monkeypatch, AbortedDuringStepProtocol)

    session = AbortedDuringStepProtocol.start_session("device")
    save_calibration_session(session)

    task = _advance(client, session.session_id, {})

    assert task["status"] == "succeeded"
    assert task["result"]["session"]["status"] == "aborted"


def test_abort_is_persisted_before_cleanup(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from pioreactor.calibrations.structured_session import load_calibration_session

    _patch_protocols(monkeypatch)
    save_calibration_session(DummyProtocol.start_session("device"))

    def cleanup(session: CalibrationSession, executor: object = None) -> None:
        persisted = load_calibration_session(session.session_id)
        assert persisted is not None
        assert persisted.status == "aborted"

    monkeypatch.setattr(DummyProtocol, "on_session_abort", cleanup)
    response = client.post("/unit_api/calibrations/sessions/session-1/abort")
    assert response.status_code == 200


def test_abort_during_advance_cleans_up_newly_started_resources(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor.calibrations.structured_session import load_calibration_session

    cleaned: list[str] = []

    class StartStep(SessionStep):
        step_id = "start"

        def render(self, ctx: SessionContext):
            return steps.info("Start", "Starting hardware")

        def advance(self, ctx: SessionContext) -> None:
            aborted = load_calibration_session(ctx.session.session_id)
            assert aborted is not None
            aborted.status = "aborted"
            save_calibration_session(aborted)
            ctx.data["job_source"] = "started-during-abort"

    class Protocol(DummyProtocol):
        step_registry = {"start": StartStep}

        @classmethod
        def on_session_abort(cls, session: CalibrationSession, executor: object = None) -> None:
            cleaned.append(session.data["job_source"])

    _use_protocol(monkeypatch, Protocol)
    session = Protocol.start_session("device")
    session.step_id = "start"
    save_calibration_session(session)
    _advance(client, session.session_id, {})
    assert cleaned == ["started-during-abort"]
    assert load_calibration_session(session.session_id).status == "aborted"


def test_stale_wait_poll_returns_current_step_without_advancing(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_protocols(monkeypatch)
    session = DummyProtocol.start_session("device")
    save_calibration_session(session)
    response = client.post(
        f"/unit_api/calibrations/sessions/{session.session_id}/inputs",
        json={"inputs": {}, "expected_step_id": "old-wait-step"},
    )
    result = client.get(response.get_json()["result_url_path"]).get_json()
    assert result["status"] == "succeeded"
    assert result["result"]["step"]["step_id"] == "intro"
