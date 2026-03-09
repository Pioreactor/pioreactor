# -*- coding: utf-8 -*-
from threading import Event
from time import sleep
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from pioreactor.actions import self_test as self_test_mod
from pioreactor.actions.self_test import click_self_test
from pioreactor.actions.self_test import get_all_tests
from pioreactor.actions.self_test import register_self_tests
from pioreactor.actions.self_test import run_tests


@pytest.fixture(autouse=True)
def reset_self_test_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(self_test_mod, "REGISTERED_SELF_TESTS", [])
    self_test_mod._ensure_plugin_self_tests_registered.cache_clear()
    monkeypatch.setattr(self_test_mod.plugin_management, "get_plugins", lambda: {})


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


def test_run_tests_times_out_and_continues_to_next_test(monkeypatch: pytest.MonkeyPatch) -> None:
    managed_state = SimpleNamespace(exit_event=Event(), publish_setting=MagicMock())
    logger = MagicMock()
    called_tests: list[str] = []
    monkeypatch.setattr("pioreactor.actions.self_test.SELF_TEST_TIMEOUT_SECONDS", 0.01)

    def times_out(managed_state, logger, unit: str, experiment: str) -> None:
        called_tests.append("times_out")
        sleep(0.1)

    def passes(managed_state, logger, unit: str, experiment: str) -> None:
        called_tests.append("passes")

    results = run_tests(
        [times_out, passes], managed_state, logger, unit="unit", testing_experiment="experiment"
    )

    assert called_tests == ["times_out", "passes"]
    assert results["count_tested"] == 2
    assert results["count_passed"] == 1
    assert results["failed_tests"] == ["times_out"]
    managed_state.publish_setting.assert_any_call("times_out", 0)
    managed_state.publish_setting.assert_any_call("passes", 1)


def test_run_tests_timeout_still_executes_test_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    managed_state = SimpleNamespace(exit_event=Event(), publish_setting=MagicMock())
    logger = MagicMock()
    cleaned_up = False
    monkeypatch.setattr("pioreactor.actions.self_test.SELF_TEST_TIMEOUT_SECONDS", 0.01)

    class Resource:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            nonlocal cleaned_up
            cleaned_up = True

    def times_out(managed_state, logger, unit: str, experiment: str) -> None:
        with Resource():
            sleep(0.1)

    results = run_tests([times_out], managed_state, logger, unit="unit", testing_experiment="experiment")

    assert cleaned_up is True
    assert results["count_tested"] == 1
    assert results["count_passed"] == 0
    assert results["failed_tests"] == ["times_out"]


def test_run_tests_does_not_swallow_keyboard_interrupt() -> None:
    managed_state = SimpleNamespace(exit_event=Event(), publish_setting=MagicMock())
    logger = MagicMock()

    def interrupted(managed_state, logger, unit: str, experiment: str) -> None:
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_tests([interrupted], managed_state, logger, unit="unit", testing_experiment="experiment")

    managed_state.publish_setting.assert_not_called()


def test_get_all_tests_includes_registered_plugin_tests_once(monkeypatch: pytest.MonkeyPatch) -> None:
    def test_air_bubble_is_running(managed_state, logger, unit: str, experiment: str) -> None:
        pass

    calls = 0

    def fake_get_plugins() -> dict:
        nonlocal calls
        calls += 1
        register_self_tests(test_air_bubble_is_running)
        return {}

    monkeypatch.setattr(self_test_mod.plugin_management, "get_plugins", fake_get_plugins)

    first_result = get_all_tests()
    second_result = get_all_tests()

    assert first_result.count(test_air_bubble_is_running) == 1
    assert second_result.count(test_air_bubble_is_running) == 1
    assert calls == 1


def test_click_self_test_filters_registered_tests_with_k(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    managed_state = SimpleNamespace(exit_event=Event(), publish_setting=MagicMock())
    logger = MagicMock()
    selected_tests: list[str] = []

    class FakeLifecycle:
        def __enter__(self):
            return managed_state

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            return None

    def test_temperature_probe(managed_state, logger, unit: str, experiment: str) -> None:
        pass

    def test_air_bubble_is_running(managed_state, logger, unit: str, experiment: str) -> None:
        pass

    def fake_run_tests(tests_to_run, managed_state, logger, unit: str, testing_experiment: str) -> dict:
        selected_tests.extend(test.__name__ for test in tests_to_run)
        return {"count_tested": len(tests_to_run), "count_passed": len(tests_to_run), "failed_tests": []}

    monkeypatch.setattr(
        self_test_mod, "get_all_tests", lambda: [test_temperature_probe, test_air_bubble_is_running]
    )
    monkeypatch.setattr(self_test_mod, "managed_lifecycle", lambda *args, **kwargs: FakeLifecycle())
    monkeypatch.setattr(self_test_mod, "create_logger", lambda *args, **kwargs: logger)
    monkeypatch.setattr(self_test_mod, "get_unit_name", lambda: "unit")
    monkeypatch.setattr(self_test_mod, "is_pio_job_running", lambda jobs: [False for _ in jobs])
    monkeypatch.setattr(self_test_mod, "run_tests", fake_run_tests)

    result = runner.invoke(click_self_test, ["-k", "air_bubble"])

    assert result.exit_code == 0
    assert selected_tests == ["test_air_bubble_is_running"]


def test_click_self_test_retry_failed_filters_to_failed_names(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    managed_state = SimpleNamespace(exit_event=Event(), publish_setting=MagicMock())
    logger = MagicMock()
    selected_tests: list[str] = []

    class FakeLifecycle:
        def __enter__(self):
            return managed_state

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            return None

    def test_temperature_probe(managed_state, logger, unit: str, experiment: str) -> None:
        pass

    def test_air_bubble_is_running(managed_state, logger, unit: str, experiment: str) -> None:
        pass

    def fake_run_tests(tests_to_run, managed_state, logger, unit: str, testing_experiment: str) -> dict:
        selected_tests.extend(test.__name__ for test in tests_to_run)
        return {"count_tested": len(tests_to_run), "count_passed": len(tests_to_run), "failed_tests": []}

    monkeypatch.setattr(
        self_test_mod, "get_all_tests", lambda: [test_temperature_probe, test_air_bubble_is_running]
    )
    monkeypatch.setattr(self_test_mod, "get_failed_test_names", lambda: iter(["test_air_bubble_is_running"]))
    monkeypatch.setattr(self_test_mod, "managed_lifecycle", lambda *args, **kwargs: FakeLifecycle())
    monkeypatch.setattr(self_test_mod, "create_logger", lambda *args, **kwargs: logger)
    monkeypatch.setattr(self_test_mod, "get_unit_name", lambda: "unit")
    monkeypatch.setattr(self_test_mod, "is_pio_job_running", lambda jobs: [False for _ in jobs])
    monkeypatch.setattr(self_test_mod, "run_tests", fake_run_tests)

    result = runner.invoke(click_self_test, ["--retry-failed"])

    assert result.exit_code == 0
    assert selected_tests == ["test_air_bubble_is_running"]
