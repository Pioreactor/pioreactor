# -*- coding: utf-8 -*-
"""
Calibration session HTTP API.

Uses step registries from calibration protocols and dispatches hardware actions
through Huey tasks defined in `core/pioreactor/web/tasks.py`.
The unit API routes here for session start/advance/abort and invokes the
calibration action executor to perform privileged hardware work.
"""
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from flask import Blueprint
from flask import jsonify
from flask import request
from flask.typing import ResponseReturnValue
from huey.exceptions import HueyException
from huey.exceptions import TaskException
from msgspec import to_builtins
from pioreactor.calibrations.registry import get_protocol
from pioreactor.calibrations.registry import get_protocol_for_session
from pioreactor.calibrations.session_flow import advance_session
from pioreactor.calibrations.session_flow import get_session_step
from pioreactor.calibrations.structured_session import load_calibration_session
from pioreactor.calibrations.structured_session import save_calibration_session
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.web.tasks import get_calibration_action
from pioreactor.web.utils import abort_with


def _execute_calibration_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    handler = get_calibration_action(action)
    task, error_label, normalize = handler(payload)
    try:
        result = task(blocking=True, timeout=300)
    except TaskException as exc:
        raise ValueError(f"{error_label} failed: {exc}") from exc
    except HueyException as exc:
        raise ValueError(f"{error_label} timed out.") from exc
    return normalize(result)


def _get_step_registry(protocol) -> Any:
    step_registry = getattr(protocol, "step_registry", None)
    if step_registry is None:
        abort_with(400, description="Protocol does not define a step registry.")
    return step_registry


def _get_calibration_step(session) -> Any:
    protocol = get_protocol_for_session(session)
    step_registry = _get_step_registry(protocol)
    return get_session_step(step_registry, session)


def start_calibration_session() -> ResponseReturnValue:
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
    step = _get_calibration_step(session)
    step_payload = to_builtins(step) if step is not None else None
    return jsonify({"session": to_builtins(session), "step": step_payload}), 201


def get_calibration_session(session_id: str) -> ResponseReturnValue:
    session = load_calibration_session(session_id)
    if session is None:
        abort_with(404, "Calibration session not found.")
    step = _get_calibration_step(session)
    step_payload = to_builtins(step) if step is not None else None
    return jsonify({"session": to_builtins(session), "step": step_payload}), 200


def abort_calibration_session_route(session_id: str) -> ResponseReturnValue:
    session = load_calibration_session(session_id)
    if session is None:
        abort_with(404, "Calibration session not found.")

    session.status = "aborted"
    session.error = "Calibration aborted by user."
    session.updated_at = utc_iso_timestamp()
    save_calibration_session(session)
    step = _get_calibration_step(session)
    step_payload = to_builtins(step) if step is not None else None
    return jsonify({"session": to_builtins(session), "step": step_payload}), 200


def advance_calibration_session(session_id: str) -> ResponseReturnValue:
    session = load_calibration_session(session_id)
    if session is None:
        abort_with(404, "Calibration session not found.")

    body = request.get_json()
    if body is None:
        abort_with(400, description="Missing JSON payload.")

    inputs = body.get("inputs", {})
    if not isinstance(inputs, dict):
        abort_with(400, description="Invalid inputs payload.")

    try:
        protocol = get_protocol_for_session(session)
        step_registry = _get_step_registry(protocol)
        session = advance_session(step_registry, session, inputs, executor=_execute_calibration_action)
    except ValueError as exc:
        abort_with(400, description=str(exc))
    except KeyError as exc:
        abort_with(400, description=str(exc))

    save_calibration_session(session)
    step = _get_calibration_step(session)
    return (
        jsonify({"session": to_builtins(session), "step": to_builtins(step) if step is not None else None}),
        200,
    )


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
