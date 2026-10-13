# -*- coding: utf-8 -*-
"""
Calibration session HTTP API.

Uses step registries from calibration protocols and dispatches hardware actions
through Huey tasks defined in `core/pioreactor/web/tasks.py`.
The unit API routes here for session start/advance/abort and invokes the
calibration action executor to perform privileged hardware work. Advancing a step
runs as a Huey task, since steps can wait minutes on hardware.
"""
# -*- coding: utf-8 -*-
from typing import Any

from flask import Blueprint
from flask import jsonify
from flask import request
from flask.typing import ResponseReturnValue
from msgspec import to_builtins
from pioreactor.calibrations.registry import get_protocol
from pioreactor.calibrations.registry import get_protocol_for_session
from pioreactor.calibrations.session_flow import get_session_step
from pioreactor.calibrations.structured_session import load_calibration_session
from pioreactor.calibrations.structured_session import save_calibration_session
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.logging import create_logger
from pioreactor.web import tasks
from pioreactor.web.utils import abort_with
from pioreactor.web.utils import create_task_response
from pioreactor.web.utils import DelayedResponseReturnValue
from pioreactor.whoami import UNIVERSAL_EXPERIMENT

logger = create_logger("unit_calibration_sessions_api", experiment=UNIVERSAL_EXPERIMENT)


def _get_step_registry(protocol: Any) -> Any:
    step_registry = getattr(protocol, "step_registry", None)
    if step_registry is None:
        abort_with(400, description="Protocol does not define a step registry.")
    return step_registry


def _get_calibration_step(session: Any) -> Any:
    protocol = get_protocol_for_session(session)
    step_registry = _get_step_registry(protocol)
    return get_session_step(step_registry, session)


def start_calibration_session() -> ResponseReturnValue:
    """
    Start a browser-driven calibration session on this unit.

    JSON body:
    {
      "target_device": "stirring",
      "protocol_name": "dc_based"
    }
    """
    body = request.get_json()
    if body is None:
        abort_with(400, description="Missing JSON payload.")

    protocol_name = body.get("protocol_name")
    target_device = body.get("target_device")
    if not target_device:
        abort_with(400, description="Missing 'target_device'.")
    if not protocol_name:
        abort_with(400, description="Missing 'protocol_name'.")

    try:
        protocol = get_protocol(target_device, protocol_name)
        start_session = getattr(protocol, "start_session", None)
        if start_session is None:
            abort_with(400, description="Protocol does not support sessions.")
        session = start_session(target_device)
    except ValueError as exc:
        abort_with(400, description=str(exc))
    except KeyError as exc:
        abort_with(400, description=str(exc))

    save_calibration_session(session)
    logger.debug(
        "Started browser protocol session: session_id=%s, target_device=%s, protocol_name=%s",
        session.session_id,
        session.target_device,
        session.protocol_name,
    )
    step = _get_calibration_step(session)
    step_payload = to_builtins(step) if step is not None else None
    response = jsonify({"session": to_builtins(session), "step": step_payload})
    response.status_code = 201
    return response


def get_calibration_session(session_id: str) -> ResponseReturnValue:
    session = load_calibration_session(session_id)
    if session is None:
        abort_with(404, "Calibration session not found.")
    step = _get_calibration_step(session)
    step_payload = to_builtins(step) if step is not None else None
    response = jsonify({"session": to_builtins(session), "step": step_payload})
    response.status_code = 200
    return response


def abort_calibration_session_route(session_id: str) -> ResponseReturnValue:
    """
    Abort a calibration session on this unit.

    No request body is required.
    """
    session = load_calibration_session(session_id)
    if session is None:
        abort_with(404, "Calibration session not found.")

    session.status = "aborted"
    session.error = "Calibration aborted by user."
    try:
        protocol = get_protocol_for_session(session)
        protocol.on_session_abort(session, executor=tasks.execute_calibration_action)
    except Exception as exc:
        logger.exception("Calibration abort cleanup failed for session %s", session_id)
        session.error = f"Calibration aborted by user. Cleanup failed: {exc}"
    session.updated_at = utc_iso_timestamp()
    save_calibration_session(session)
    step = _get_calibration_step(session)
    step_payload = to_builtins(step) if step is not None else None
    response = jsonify({"session": to_builtins(session), "step": step_payload})
    response.status_code = 200
    return response


def advance_calibration_session(session_id: str) -> DelayedResponseReturnValue:
    """
    Submit inputs for the current step of a calibration session on this unit.

    JSON body:
    {
      "inputs": {
        "field_name": "field value"
      }
    }

    Answers 202 with a task: poll `result_url_path` (or the leader's
    /api/workers/<unit>/task_results/<task_id>). Its `result` is
    {"session", "step"}; a rejected input or failed action reports `failed`.
    """
    session = load_calibration_session(session_id)
    if session is None:
        abort_with(404, "Calibration session not found.")

    body = request.get_json()
    if body is None:
        abort_with(400, description="Missing JSON payload.")

    inputs = body.get("inputs", {})
    if not isinstance(inputs, dict):
        abort_with(400, description="Invalid inputs payload.")

    return create_task_response(tasks.advance_calibration_session_task(session_id, inputs))


def register_calibration_session_routes(unit_api_bp: Blueprint) -> None:
    unit_api_bp.add_url_rule("/calibrations/sessions", view_func=start_calibration_session, methods=["POST"])
    unit_api_bp.add_url_rule(
        "/calibrations/sessions/<session_id>", view_func=get_calibration_session, methods=["GET"]
    )
    unit_api_bp.add_url_rule(
        "/calibrations/sessions/<session_id>/abort",
        view_func=abort_calibration_session_route,
        methods=["POST"],
    )
    unit_api_bp.add_url_rule(
        "/calibrations/sessions/<session_id>/inputs",
        view_func=advance_calibration_session,
        methods=["POST"],
    )
