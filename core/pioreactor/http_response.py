# -*- coding: utf-8 -*-
from msgspec import DecodeError
from msgspec import Struct
from msgspec import ValidationError
from msgspec.json import decode as json_decode
from pioreactor.experiment_profiles.validate import Diagnostic
from pioreactor.mureq import Response


class UnitApiErrorPayload(Struct, forbid_unknown_fields=True, omit_defaults=True):
    error: str
    status: int
    cause: str | None = None
    remediation: str | None = None
    diagnostics: list[Diagnostic] | None = None


def decode_unit_api_error_payload(
    response: Response | None,
) -> UnitApiErrorPayload | None:
    if response is None or not response.body:
        return None

    try:
        payload = json_decode(response.body, type=UnitApiErrorPayload)
    except (DecodeError, ValidationError):
        return None

    return payload if payload.status == response.status_code else None


def summarize_error_response(response: Response) -> str:
    payload = decode_unit_api_error_payload(response)
    if payload is None:
        return f"HTTP {response.status_code}."

    details = [f"HTTP {payload.status}: {payload.error}"]
    if payload.cause:
        details.append(f"Cause: {payload.cause}")
    if payload.remediation:
        details.append(f"Remediation: {payload.remediation}")
    return " ".join(details)
