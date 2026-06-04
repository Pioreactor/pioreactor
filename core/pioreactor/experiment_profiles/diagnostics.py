# -*- coding: utf-8 -*-
from typing import Literal

from msgspec import Struct


class Diagnostic(Struct, forbid_unknown_fields=True, omit_defaults=True):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    path: str
    hint: str | None = None
