# -*- coding: utf-8 -*-
# utils.py
from __future__ import annotations

import re
from time import time
from typing import NewType

from flask import jsonify
from flask import Response
from flask.typing import ResponseReturnValue
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_unit_name


def attach_cache_control(response: Response, max_age=5) -> Response:
    """
    Takes in a Flask Response object and sets the Cache-Control header
    to 'public, max-age=<max_age>'.
    """
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    return response


DelayedResponseReturnValue = NewType("DelayedResponseReturnValue", ResponseReturnValue)


def create_task_response(task) -> DelayedResponseReturnValue:
    return (
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
        if cache.get(job) and (time() - cache.get(job)) < expire_time_seconds:
            return True
        else:
            cache.set(job, time())
            return False
