# -*- coding: utf-8 -*-
from subprocess import CalledProcessError
from subprocess import CompletedProcess
from subprocess import TimeoutExpired
from unittest.mock import Mock

import pytest
from pioreactor.utils.clock import is_clock_synchronized


@pytest.mark.parametrize(
    ("output", "expected"), [("yes\n", True), ("no\n", False), ("", None), ("unexpected", None)]
)
def test_clock_sync_status(monkeypatch: pytest.MonkeyPatch, output: str, expected: bool | None) -> None:
    command = Mock(return_value=CompletedProcess([], 0, stdout=output))
    monkeypatch.setattr("pioreactor.utils.clock.run", command)

    assert is_clock_synchronized() is expected
    command.assert_called_once_with(
        ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
        check=True,
        capture_output=True,
        text=True,
        timeout=2,
    )


@pytest.mark.parametrize(
    "error", [FileNotFoundError(), CalledProcessError(1, "timedatectl"), TimeoutExpired("timedatectl", 2)]
)
def test_clock_sync_unavailable(
    monkeypatch: pytest.MonkeyPatch, error: OSError | CalledProcessError | TimeoutExpired
) -> None:
    monkeypatch.setattr("pioreactor.utils.clock.run", Mock(side_effect=error))
    assert is_clock_synchronized() is None
