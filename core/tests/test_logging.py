# -*- coding: utf-8 -*-
import json
import logging

from pioreactor.logging import CustomisedJSONFormatter


class DummyLogger:
    def debug(self, *args, **kwargs) -> None:
        pass

    def notice(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass

    def error(self, *args, **kwargs) -> None:
        pass


def test_customised_json_formatter_strips_ansi_decodes_bytes_and_normalizes_newlines() -> None:
    formatter = CustomisedJSONFormatter()
    record = logging.LogRecord(
        name="install_plugin",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=b"\x1b[36mline1\r\nline2\x1b[0m",
        args=(),
        exc_info=None,
    )
    record.source = "app"  # type: ignore[attr-defined]

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "line1\nline2"
    assert payload["level"] == "DEBUG"
    assert payload["task"] == "install_plugin"
