# -*- coding: utf-8 -*-
import re


_ALLOWED_UNIX_FILENAME = re.compile(r"^[A-Za-z0-9._-]+( [A-Za-z0-9._-]+)*$")


def is_valid_unix_filename(name: str, *, max_bytes: int = 255) -> bool:
    """
    Return True iff *name* is a single portable filename component.

    Artifact names are path components, not arbitrary strings. Validate them
    before constructing calibration, estimator, profile, or descriptor paths.
    """
    if not name:
        return False
    if name in {".", ".."}:
        return False
    if name[0] in ".-":
        return False
    if "/" in name or "\\" in name:
        return False
    if any(ord(c) < 0x20 for c in name):
        return False
    if len(name.encode()) > max_bytes:
        return False
    return bool(_ALLOWED_UNIX_FILENAME.fullmatch(name))
