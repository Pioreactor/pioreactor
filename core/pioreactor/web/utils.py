# -*- coding: utf-8 -*-
# utils.py
import re
import typing as t
from pathlib import Path
from time import time
from typing import NewType
from typing import NoReturn

from flask import abort
from flask import jsonify
from flask import Response
from flask.typing import ResponseReturnValue
from msgspec import DecodeError
from msgspec import Struct
from msgspec import to_builtins
from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from pioreactor import structs
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_unit_name


class UnitApiErrorPayload(Struct, omit_defaults=True):
    error: str
    status: int
    cause: str | None = None
    remediation: str | None = None


class CachedGetEntry(Struct):
    value: t.Any
    cached_at: float


def abort_with(
    status: int,
    description: str,
    *,
    remediation: str | None = None,
    cause: str | None = None,
) -> NoReturn:
    if remediation is None and cause is None:
        abort(status, description=description)
        raise AssertionError("abort should not return")

    payload = UnitApiErrorPayload(
        error=description,
        status=status,
        cause=cause,
        remediation=remediation,
    )
    response = jsonify(t.cast(dict[str, t.Any], to_builtins(payload)))
    response.status_code = status
    abort(response)
    raise AssertionError("abort should not return")


def ensure_error_info(payload: dict[str, t.Any], status: int) -> UnitApiErrorPayload:
    message = _extract_error_message(payload)
    cause = payload.get("cause")
    normalized_cause = cause.strip() if isinstance(cause, str) and cause.strip() else message
    remediation = payload.get("remediation")
    normalized_remediation = (
        remediation.strip() if isinstance(remediation, str) and remediation.strip() else None
    )

    normalized_payload = UnitApiErrorPayload(
        status=status,
        error=message,
        cause=normalized_cause,
        remediation=normalized_remediation,
    )

    return normalized_payload


def _extract_error_message(payload: dict[str, t.Any]) -> str:
    value = payload.get("error")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "Request failed."


def attach_cache_control(response: Response, max_age: int = 5) -> Response:
    """
    Takes in a Flask Response object and sets the Cache-Control header
    to 'public, max-age=<max_age>'.
    """
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    return response


DelayedResponseReturnValue = NewType("DelayedResponseReturnValue", ResponseReturnValue)  # type: ignore


def create_task_response(task: t.Any) -> DelayedResponseReturnValue:
    return (  # type: ignore
        jsonify(
            {
                "unit": get_unit_name(),
                "task_id": task.id,
                "result_url_path": f"/unit_api/task_results/{task.id}",
            }
        ),
        202,
    )


def scrub_to_valid(value: str) -> str:
    if value is None:
        raise ValueError()
    elif value.startswith("sqlite_"):
        raise ValueError()
    return "".join(chr for chr in value if (chr.isalnum() or chr == "_"))


_ALLOWED = re.compile(r"^[A-Za-z0-9._-]+( [A-Za-z0-9._-]+)*$")  # single spaces only


def is_valid_unix_filename(name: str, *, max_bytes: int = 255) -> bool:
    """
    Return True iff *name* is a single portable filename component.

    Rules
    -----
    • ASCII letters, digits, dot, underscore, dash, single spaces
    • No leading dot or dash
    • Not '.' or '..'
    • No slash, backslash, or control chars
    • Max 255 bytes in UTF‑8
    """
    if name in {".", ".."}:
        return False
    if name[0] in ".-":
        return False
    if "/" in name or "\\" in name:
        return False
    if any(ord(c) < 0x20 for c in name):  # control chars (NUL already caught)
        return False
    if len(name.encode()) > max_bytes:
        return False
    return bool(_ALLOWED.fullmatch(name))


def is_rate_limited(job: str, expire_time_seconds: float = 1.0) -> bool:
    """
    Check if the user has made a request within the debounce duration.
    """
    with local_intermittent_storage("debounce") as cache:
        now = time()
        if cache.set_if_absent(job, now):
            return False

        last_request_time = cache.get(job)
        if (last_request_time is not None) and (
            (now - float(t.cast(float | int | str, last_request_time))) < expire_time_seconds
        ):
            return True

        cache.set(job, now)
        return False


def load_background_job_descriptors(
    dot_pioreactor_path: Path,
    *,
    report_error: t.Callable[[str], None] | None = None,
) -> list[structs.BackgroundJobDescriptor]:
    job_path_builtins = dot_pioreactor_path / "ui" / "jobs"
    job_path_plugins = dot_pioreactor_path / "plugins" / "ui" / "jobs"
    files = sorted(job_path_builtins.glob("*.y*ml")) + sorted(job_path_plugins.glob("*.y*ml"))

    parsed_yaml: dict[str, structs.BackgroundJobDescriptor] = {}

    for file in files:
        try:
            decoded_yaml = yaml_decode(file.read_bytes(), type=structs.BackgroundJobDescriptor)
            parsed_yaml[decoded_yaml.job_name] = decoded_yaml
        except (ValidationError, DecodeError) as e:
            if report_error is not None:
                report_error(f"Yaml error in {file.name}: {e}")

    return list(parsed_yaml.values())


def load_automation_descriptors(
    dot_pioreactor_path: Path,
    automation_type: str,
    *,
    report_error: t.Callable[[str], None] | None = None,
) -> list[structs.AutomationDescriptor]:
    automation_path_builtins = dot_pioreactor_path / "ui" / "automations" / automation_type
    automation_path_plugins = dot_pioreactor_path / "plugins" / "ui" / "automations" / automation_type
    files = sorted(automation_path_builtins.glob("*.y*ml")) + sorted(automation_path_plugins.glob("*.y*ml"))

    parsed_yaml: dict[str, structs.AutomationDescriptor] = {}

    for file in files:
        try:
            decoded_yaml = yaml_decode(file.read_bytes(), type=structs.AutomationDescriptor)
            parsed_yaml[decoded_yaml.automation_name] = decoded_yaml
        except (ValidationError, DecodeError) as e:
            if report_error is not None:
                report_error(f"Yaml error in {file.name}: {e}")

    return list(parsed_yaml.values())
