# -*- coding: utf-8 -*-
# utils.py
import re
import typing as t
from time import time
from typing import NewType
from typing import NoReturn

from flask import abort
from flask import jsonify
from flask import Response
from flask.typing import ResponseReturnValue
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_unit_name


def abort_with(
    status: int,
    description: str,
    *,
    error_info: dict[str, t.Any] | None = None,
    remediation: str | None = None,
    cause: str | None = None,
) -> NoReturn:
    if error_info is None and remediation is None and cause is None:
        abort(status, description=description)
        raise AssertionError("abort should not return")

    payload: dict[str, t.Any] = {"error": description}
    merged_error_info: dict[str, t.Any] = {}
    if isinstance(error_info, dict):
        merged_error_info.update(error_info)
    if remediation is not None:
        merged_error_info["remediation"] = remediation
    if cause is not None:
        merged_error_info["cause"] = cause
    if merged_error_info:
        payload["error_info"] = merged_error_info

    response = jsonify(payload)
    response.status_code = status
    abort(response)
    raise AssertionError("abort should not return")


def ensure_error_info(payload: dict[str, t.Any], status: int) -> dict[str, t.Any]:
    message = _extract_error_message(payload)
    if not isinstance(payload.get("error"), str):
        payload["error"] = message

    error_info = payload.get("error_info")
    if not isinstance(error_info, dict):
        error_info = {}
    if "message" in error_info:
        error_info.pop("message", None)

    error_info.setdefault("cause", message)
    error_info.setdefault("remediation", _default_remediation_for_status(status))
    error_info.setdefault("status", status)

    payload["error_info"] = error_info
    return payload


def _extract_error_message(payload: dict[str, t.Any]) -> str:
    for key in ("error", "description"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested_value = value.get("error") or value.get("description")
            if isinstance(nested_value, str) and nested_value.strip():
                return nested_value.strip()
    return "Request failed."


_DEFAULT_REMEDIATIONS = {
    400: "Check required fields and request format, then retry.",
    401: "Authenticate and retry the request.",
    403: "Verify permissions and configuration allow this action.",
    404: "Confirm the resource exists and the URL is correct.",
    409: "Resolve the conflicting state, then retry.",
    429: "Wait briefly before retrying to avoid rate limits.",
    502: "Check leader/worker connectivity and retry.",
    503: "Service is unavailable; retry after a short delay.",
}


def _default_remediation_for_status(status: int) -> str:
    return _DEFAULT_REMEDIATIONS.get(status, "Check server logs for details and retry.")


def attach_cache_control(response: Response, max_age=5) -> Response:
    """
    Takes in a Flask Response object and sets the Cache-Control header
    to 'public, max-age=<max_age>'.
    """
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    return response


DelayedResponseReturnValue = NewType("DelayedResponseReturnValue", ResponseReturnValue)  # type: ignore


def create_task_response(task) -> DelayedResponseReturnValue:
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


def is_rate_limited(job: str, expire_time_seconds=1.0) -> bool:
    """
    Check if the user has made a request within the debounce duration.
    """
    with local_intermittent_storage("debounce") as cache:
        now = time()
        if cache.set_if_absent(job, now):
            return False

        last_request_time = cache.get(job)
        if (last_request_time is not None) and ((now - float(last_request_time)) < expire_time_seconds):
            return True

        cache.set(job, now)
        return False
