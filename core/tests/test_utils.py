# -*- coding: utf-8 -*-
# test_utils
from contextlib import redirect_stdout
from io import StringIO

import pytest
from pioreactor import whoami
from pioreactor.background_jobs.stirring import start_stirring
from pioreactor.exc import NotActiveWorkerError
from pioreactor.utils import argextrema
from pioreactor.utils import callable_stack
from pioreactor.utils import get_running_pio_job_id
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage
from pioreactor.utils import managed_lifecycle
from pioreactor.utils import SummableDict
from pioreactor.whoami import get_unit_name


class DummyMQTTClient:
    def __init__(self):
        self.published: list[tuple[str, str, bool]] = []

    def publish(self, topic, payload, retain=True):
        self.published.append((topic, payload, retain))

    def message_callback_add(self, *args, **kwargs):
        return None

    def subscribe(self, *args, **kwargs):
        return None


def test_that_out_scope_caches_cant_access_keys_created_by_inner_scope_cache() -> None:
    """
    You can modify caches, and the last assignment is valid.
    """
    with local_intermittent_storage("test") as cache:
        for k in cache.iterkeys():
            del cache[k]

    with local_intermittent_storage("test") as cache1:
        cache1["A"] = "0"

        with local_intermittent_storage("test") as cache2:
            assert cache2["A"] == "0"
            cache2["B"] = "1"

        assert "B" in cache1
        cache1["B"] = "2"

    with local_intermittent_storage("test") as cache:
        assert cache["A"] == "0"
        assert cache["B"] == "2"


def test_caches_will_always_save_the_lastest_value_provided() -> None:
    with local_intermittent_storage("test") as cache:
        cache.empty()

    with local_intermittent_storage("test") as cache:
        cache["A"] = "1"
        cache["A"] = "0"
        cache["B"] = "2"

    with local_intermittent_storage("test") as cache:
        assert cache["A"] == "0"
        assert cache["B"] == "2"


def test_caches_will_delete_when_asked() -> None:
    with local_intermittent_storage("test") as cache:
        for k in cache.iterkeys():
            del cache[k]

    with local_intermittent_storage("test") as cache:
        cache["test"] = "1"

    with local_intermittent_storage("test") as cache:
        assert "test" in cache
        del cache["test"]
        assert "test" not in cache


def test_caches_pop() -> None:
    with local_intermittent_storage("test") as cache:
        cache.empty()

    with local_intermittent_storage("test") as cache:
        cache["A"] = "1"

    with local_intermittent_storage("test") as cache:
        assert cache.pop("A") == "1"
        assert cache.pop("B") is None
        assert cache.pop("C", default=3) == 3


def test_cache_set_if_absent() -> None:
    with local_intermittent_storage("test") as cache:
        cache.empty()

    with local_intermittent_storage("test") as cache:
        assert cache.set_if_absent("A", "1")
        assert not cache.set_if_absent("A", "2")

    with local_intermittent_storage("test") as cache:
        assert cache["A"] == "1"


def test_caches_can_have_tuple_or_singleton_keys() -> None:
    with local_persistent_storage("test_caches_can_have_tuple_keys") as c:
        c[(1, 2)] = 1
        c[("a", "b")] = 2
        c[("a", None)] = 3
        c[4] = 4
        c["5"] = 5

    with local_persistent_storage("test_caches_can_have_tuple_keys") as c:
        assert list(c.iterkeys()) == [4, "5", ["a", "b"], ["a", None], [1, 2]]


def test_caches_integer_keys() -> None:
    with local_persistent_storage("test_caches_integer_keys") as c:
        c[1] = "a"
        c[2] = "b"

    with local_persistent_storage("test_caches_integer_keys") as c:
        assert list(c.iterkeys()) == [1, 2]


def test_caches_str_keys_as_ints_stay_as_str() -> None:
    with local_persistent_storage("test_caches_str_keys_as_ints_stay_as_str") as c:
        c["1"] = "a"
        c["2"] = "b"

    with local_persistent_storage("test_caches_str_keys_as_ints_stay_as_str") as c:
        assert list(c.iterkeys()) == ["1", "2"]


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


def greet(name):
    print(f"Hello, {name}!")


def goodbye(name):
    print(f"Goodbye, {name}!")


def test_callable_stack_append_and_call() -> None:
    my_stack = callable_stack()
    my_stack.append(greet)
    my_stack.append(goodbye)

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == "Goodbye, Alice!\nHello, Alice!\n"


def test_callable_stack_empty_call() -> None:
    def default_function(name):
        print(f"Default function called, {name}")

    my_stack = callable_stack(default_function_if_empty=default_function)

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == "Default function called, Alice\n"


def test_callable_stack_no_default() -> None:
    my_stack = callable_stack()

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == ""


@pytest.mark.parametrize(
    "functions,expected_output",
    [
        ([greet], "Hello, Alice!\n"),
        ([goodbye], "Goodbye, Alice!\n"),
        ([greet, goodbye], "Goodbye, Alice!\nHello, Alice!\n"),
    ],
)
def test_callable_stack_multiple_append_and_call(functions, expected_output) -> None:
    my_stack = callable_stack()

    for function in functions:
        my_stack.append(function)

    with StringIO() as output, redirect_stdout(output):
        my_stack("Alice")
        assert output.getvalue() == expected_output


def test_argextrema_with_empty_lists() -> None:
    with pytest.raises(ValueError):
        argextrema([])


def test_summable_dict_with_list_values() -> None:
    first = SummableDict({"a": [1.0, 2.0], "b": [3.0]})
    second = SummableDict({"a": [4.0], "c": [5.0, 6.0]})

    result = first + second

    assert result["a"] == [1.0, 2.0, 4.0]
    assert result["b"] == [3.0]
    assert result["c"] == [5.0, 6.0]
