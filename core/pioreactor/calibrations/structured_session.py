# -*- coding: utf-8 -*-
"""
Protocol session structures used by calibrator/estimator workflows.
"""
from typing import Any
from typing import Literal

from msgspec import Struct
from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_timestamp

SessionStatus = Literal["in_progress", "complete", "failed", "aborted"]
StepType = Literal["info", "confirm", "form", "action", "result"]
FieldType = Literal["string", "float", "int", "bool", "float_list", "choice"]


class CalibrationStepField(Struct, kw_only=True):
    name: str
    label: str
    field_type: FieldType
    required: bool = True
    default: Any | None = None
    options: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    help_text: str | None = None


class CalibrationStep(Struct, kw_only=True):
    step_id: str
    step_type: StepType
    title: str | None = None
    body: str | None = None
    fields: list[CalibrationStepField] = []
    metadata: dict[str, Any] = {}


class CalibrationSession(Struct, kw_only=True, frozen=False):
    session_id: str
    protocol_name: str
    target_device: str
    status: SessionStatus
    step_id: str
    data: dict[str, Any]
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


def utc_iso_timestamp() -> str:
    return current_utc_timestamp()


def save_calibration_session(session: CalibrationSession) -> None:
    payload = json_encode(session)
    with local_persistent_storage("calibration_sessions") as store:
        store[session.session_id] = payload


def load_calibration_session(session_id: str) -> CalibrationSession | None:
    with local_persistent_storage("calibration_sessions") as store:
        payload = store.get(session_id)
    if payload is None:
        return None
    return json_decode(payload, type=CalibrationSession)
