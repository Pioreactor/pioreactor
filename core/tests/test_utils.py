# -*- coding: utf-8 -*-
# test_utils
import gc
import signal
import weakref
from unittest.mock import MagicMock

import pytest
from pioreactor import whoami
from pioreactor.background_jobs.stirring import start_stirring
from pioreactor.exc import NotActiveWorkerError
from pioreactor.utils import argextrema
from pioreactor.utils import boolean_retry
from pioreactor.utils import clamp
from pioreactor.utils import get_running_pio_job_id
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import managed_lifecycle
from pioreactor.utils import SummableDict
from pioreactor.whoami import get_unit_name


class DummyMQTTClient:
    def __init__(self):
        self.published: list[tuple[str, str, bool]] = []
        self.callbacks: dict[str, object] = {}
        self.subscriptions: list[str] = []
        self.unsubscribed: list[str] = []

    def publish(self, topic, payload, retain=True, **kwargs):
        self.published.append((topic, payload, retain))

    def message_callback_add(self, topic, callback):
        self.callbacks[topic] = callback

    def message_callback_remove(self, topic):
        self.callbacks.pop(topic, None)

    def subscribe(self, topic, *args, **kwargs):
        self.subscriptions.append(topic)

    def unsubscribe(self, topic):
        self.unsubscribed.append(topic)


def test_is_pio_job_running_single() -> None:
    experiment = "test_is_pio_job_running_single"
    unit = get_unit_name()

    assert not is_pio_job_running("stirring")
    assert not is_pio_job_running("od_reading")

    with start_stirring(target_rpm=0, experiment=experiment, unit=unit):
        assert is_pio_job_running("stirring")
        assert not is_pio_job_running("od_reading")

    assert not is_pio_job_running("stirring")
    assert not is_pio_job_running("od_reading")


def test_is_pio_job_running_multiple() -> None:
    experiment = "test_is_pio_job_running_multiple"
    unit = get_unit_name()

    assert not any(is_pio_job_running(["stirring", "od_reading"]))
    assert is_pio_job_running(["stirring"]) == [False]

    with start_stirring(target_rpm=0, experiment=experiment, unit=unit):
        assert any(is_pio_job_running(["stirring", "od_reading"]))
        assert is_pio_job_running(["stirring", "od_reading"]) == [True, False]
        assert is_pio_job_running(["od_reading", "stirring"]) == [False, True]
        assert is_pio_job_running(["stirring"]) == [True]

    assert not any(is_pio_job_running(["stirring", "od_reading"]))
    assert is_pio_job_running(["stirring"]) == [False]


def test_get_running_pio_job_id_single() -> None:
    experiment = "test_get_running_pio_job_id_single"
    unit = get_unit_name()

    assert get_running_pio_job_id("stirring") is None

    with start_stirring(target_rpm=0, experiment=experiment, unit=unit):
        job_id = get_running_pio_job_id("stirring")
        assert job_id is not None
        assert isinstance(job_id, int)

    assert get_running_pio_job_id("stirring") is None


def test_mqtt_disconnect_exit() -> None:
    unit = "test_unit"
    experiment = "test_mqtt_disconnect_exit"
    name = "test_name"

    client = DummyMQTTClient()
    with managed_lifecycle(unit, experiment, name, mqtt_client=client, exit_on_mqtt_disconnect=True) as state:
        state._on_disconnect()  # Simulate broker disconnect
        state.block_until_disconnected()  # exits immediately
        assert state.exit_event.is_set()


def test_managed_lifecycle_requires_active_unit(monkeypatch) -> None:
    monkeypatch.setattr(whoami, "is_active", lambda unit: False)

    with pytest.raises(NotActiveWorkerError):
        managed_lifecycle("inactive_unit", "test_ignore_flag", "test_job", mqtt_client=DummyMQTTClient())


def test_managed_lifecycle_can_ignore_inactive_state(monkeypatch) -> None:
    monkeypatch.setattr(whoami, "is_active", lambda unit: False)
    client = DummyMQTTClient()

    with managed_lifecycle(
        "inactive_unit",
        "test_ignore_flag",
        "test_job",
        mqtt_client=client,
        ignore_is_active_state=True,
    ) as lifecycle:
        assert lifecycle.state == "ready"

    assert lifecycle.exit_event.is_set()
    assert [payload for _, payload, _ in client.published] == ["init", "ready", "disconnected"]


def test_managed_lifecycle_cleans_up_signal_handlers_and_reused_client_callbacks() -> None:
    unit = "test_unit"
    experiment = "test_managed_lifecycle_cleanup"
    name = "test_job"
    client = DummyMQTTClient()

    initial_sigterm_handler = signal.getsignal(signal.SIGTERM)
    initial_sigint_handler = signal.getsignal(signal.SIGINT)

    lifecycle_ref: weakref.ReferenceType[managed_lifecycle] | None = None

    try:
        with managed_lifecycle(
            unit,
            experiment,
            name,
            mqtt_client=client,
            ignore_is_active_state=True,
        ) as lifecycle:
            lifecycle_ref = weakref.ref(lifecycle)
            assert len(client.callbacks) == 4
        del lifecycle

        gc.collect()

        assert client.callbacks == {}
        assert len(client.unsubscribed) == 4
        assert signal.getsignal(signal.SIGTERM) == initial_sigterm_handler
        assert signal.getsignal(signal.SIGINT) == initial_sigint_handler
        assert lifecycle_ref is not None
        assert lifecycle_ref() is None
    finally:
        signal.signal(signal.SIGTERM, initial_sigterm_handler)
        signal.signal(signal.SIGINT, initial_sigint_handler)


def test_managed_lifecycle_waits_for_disconnected_publish_before_shutdown() -> None:
    client = DummyMQTTClient()
    publish_info = MagicMock()
    client.publish = MagicMock(return_value=publish_info)
    client.shutdown = MagicMock()

    with managed_lifecycle(
        "test_unit",
        "test_waits_for_publish",
        "test_job",
        mqtt_client=client,
        ignore_is_active_state=True,
    ):
        pass

    publish_info.wait_for_publish.assert_called_once_with(timeout=5)


def test_argextrema_with_empty_lists() -> None:
    with pytest.raises(ValueError):
        argextrema([])


def test_clamp_returns_bounded_values() -> None:
    assert clamp(0, -1, 10) == 0
    assert clamp(0, 3, 10) == 3
    assert clamp(0, 12, 10) == 10


def test_boolean_retry_uses_independent_default_kwargs() -> None:
    seen_kwargs: list[dict[str, object]] = []

    def func(*, marker: object | None = None) -> bool:
        seen_kwargs.append({"marker": marker})
        return len(seen_kwargs) == 2

    assert boolean_retry(func, retries=2, sleep_for=0.0) is True
    assert seen_kwargs == [{"marker": None}, {"marker": None}]


def test_summable_dict_with_list_values() -> None:
    first = SummableDict({"a": [1.0, 2.0], "b": [3.0]})
    second = SummableDict({"a": [4.0], "c": [5.0, 6.0]})

    result = first + second

    assert result["a"] == [1.0, 2.0, 4.0]
    assert result["b"] == [3.0]
    assert result["c"] == [5.0, 6.0]


def test_summable_dict_iadd_mutates_in_place() -> None:
    first = SummableDict({"a": 1.0})
    second = SummableDict({"a": 2.0, "b": 3.0})

    result = first
    result += second

    assert result is first
    assert first["a"] == 3.0
    assert first["b"] == 3.0


def test_summable_dict_missing_key_returns_zero() -> None:
    result = SummableDict({"a": 1.0})

    assert result["missing"] == 0.0
