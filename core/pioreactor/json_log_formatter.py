# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    Minimal JSON log formatter compatible with our prior json_log_formatter usage.
    """

    _skip_record_keys = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }

    def json_record(self, message: str, extra: dict[str, Any], record: logging.LogRecord) -> dict[str, Any]:
        payload = dict(extra)
        payload["message"] = message
        return payload

    def to_json(self, record: dict[str, Any]) -> str:
        return json.dumps(record, default=self._default_json, separators=(",", ":"))

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        extra = self._extract_extra(record)
        json_record = self.json_record(message, extra, record)
        return self.to_json(json_record)

    def _extract_extra(self, record: logging.LogRecord) -> dict[str, Any]:
        extras: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in self._skip_record_keys or key.startswith("_"):
                continue
            extras[key] = value
        return extras

    @staticmethod
    def _default_json(value: Any) -> str:
        return str(value)
