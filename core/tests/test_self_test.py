# -*- coding: utf-8 -*-
import os
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DOT_PIOREACTOR", ".pioreactor")

from pioreactor.actions.self_test import run_tests


def test_run_tests_success_and_failure_counts() -> None:
    managed_state = SimpleNamespace(exit_event=Event(), publish_setting=MagicMock())
    logger = MagicMock()
    called_tests: list[str] = []

    def passes(managed_state, logger, unit: str, experiment: str) -> None:
        called_tests.append("passes")

    def fails(managed_state, logger, unit: str, experiment: str) -> None:
        called_tests.append("fails")
        raise RuntimeError("boom")

    results = run_tests([passes, fails], managed_state, logger, unit="unit", testing_experiment="experiment")

    assert called_tests == ["passes", "fails"]
    assert results["count_tested"] == 2
    assert results["count_passed"] == 1
    assert results["failed_tests"] == ["fails"]
    managed_state.publish_setting.assert_any_call("passes", 1)
    managed_state.publish_setting.assert_any_call("fails", 0)


def test_run_tests_stops_when_exit_event_is_set() -> None:
    managed_state = SimpleNamespace(exit_event=Event(), publish_setting=MagicMock())
    logger = MagicMock()
    called_tests: list[str] = []

    def first_test(managed_state, logger, unit: str, experiment: str) -> None:
        called_tests.append("first")
        managed_state.exit_event.set()

    def second_test(managed_state, logger, unit: str, experiment: str) -> None:
        called_tests.append("second")

    results = run_tests(
        [first_test, second_test], managed_state, logger, unit="unit", testing_experiment="experiment"
    )

    assert called_tests == ["first"]
    assert results["count_tested"] == 1
    assert results["count_passed"] == 1
    assert results["failed_tests"] == []
    managed_state.publish_setting.assert_called_once_with("first_test", 1)


def test_run_tests_does_not_swallow_keyboard_interrupt() -> None:
    managed_state = SimpleNamespace(exit_event=Event(), publish_setting=MagicMock())
    logger = MagicMock()

    def interrupted(managed_state, logger, unit: str, experiment: str) -> None:
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_tests([interrupted], managed_state, logger, unit="unit", testing_experiment="experiment")

    managed_state.publish_setting.assert_not_called()
