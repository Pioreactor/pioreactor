# -*- coding: utf-8 -*-
# test_utils
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO

import pytest
from msgspec.json import encode as dumps

from pioreactor.background_jobs.stirring import start_stirring
from tests.conftest import capture_requests
from pioreactor.utils import argextrema
from pioreactor.utils import callable_stack
from pioreactor.utils import ClusterJobManager
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import JobManager
from pioreactor.utils import JobMetadataKey
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage
from pioreactor.utils import managed_lifecycle
from pioreactor.whoami import get_unit_name


@pytest.mark.xfail(reason="Don't use nested caches like this!")
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

    with start_stirring(target_rpm=0, experiment=experiment, unit=unit):
        assert any(is_pio_job_running(["stirring", "od_reading"]))
        assert is_pio_job_running(["stirring", "od_reading"]) == [True, False]
        assert is_pio_job_running(["od_reading", "stirring"]) == [False, True]

    assert not any(is_pio_job_running(["stirring", "od_reading"]))


def test_mqtt_disconnect_exit() -> None:
    unit = "test_unit"
    experiment = "test_mqtt_disconnect_exit"
    name = "test_name"

    with managed_lifecycle(unit, experiment, name, exit_on_mqtt_disconnect=True) as state:
        state.mqtt_client.disconnect()  # Simulate a disconnect
        state.block_until_disconnected()  # exits immediately


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


@pytest.fixture
def job_manager():
    with JobManager() as jm:
        yield jm


@pytest.fixture
def job_id(job_manager):
    # Register a job to get a job_id to use in upsert tests
    return job_manager.register_and_set_running(
        unit="unit_test",
        experiment="experiment_test",
        job_name="test_job",
        job_source="source_test",
        pid=12345,
        leader="leader_test",
        is_long_running_job=False,
    )


def test_create_table(job_manager: JobManager) -> None:
    assert (
        job_manager.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pio_job_metadata'"
        ).fetchone()
        is not None
    )


def test_register_and_set_running(job_manager: JobManager) -> None:
    job_key = job_manager.register_and_set_running(
        "test_unit", "test_experiment", "test_name", "test_source", 12345, "test_leader", False
    )
    assert isinstance(job_key, JobMetadataKey)
    job = job_manager.conn.execute(
        "SELECT unit, experiment, job_name, job_source, pid, leader, is_running, is_long_running_job FROM pio_job_metadata WHERE job_id=?",
        (job_key,),
    ).fetchone()
    assert job is not None
    assert job[0] == "test_unit"
    assert job[1] == "test_experiment"
    assert job[2] == "test_name"
    assert job[3] == "test_source"
    assert job[4] == 12345
    assert job[5] == "test_leader"
    assert job[6] == 1
    assert job[7] == 0
    job_manager.set_not_running(job_key)


def test_set_not_running(job_manager: JobManager) -> None:
    job_key = job_manager.register_and_set_running(
        "test_unit", "test_experiment", "test_name", "test_source", 12345, "test_leader", False
    )
    job_manager.set_not_running(job_key)
    job = job_manager.conn.execute(
        "SELECT is_running FROM pio_job_metadata WHERE job_id=?", (job_key,)
    ).fetchone()
    assert job is not None
    assert job[0] == 0


def test_can_kill_long_running_job_if_request(job_manager: JobManager) -> None:
    is_long_running = True
    job_key = job_manager.register_and_set_running(
        "test_unit", "test_experiment", "monitor", "test_source", 12345, "test_leader", is_long_running
    )
    assert job_manager.kill_jobs(job_name="monitor") == 1
    # clean up
    job_manager.set_not_running(job_key)


def test_is_job_running(job_manager: JobManager) -> None:
    job_key = job_manager.register_and_set_running(
        "test_unit", "test_experiment", "test_name", "test_source", 12345, "test_leader", False
    )
    assert job_manager.is_job_running("test_name") is True
    job_manager.set_not_running(job_key)
    assert job_manager.is_job_running("test_name") is False


def test_ClusterJobManager_sends_requests() -> None:
    workers = ("pio01", "pio02", "pio03")
    with capture_requests() as bucket:
        with ClusterJobManager() as cm:
            cm.kill_jobs(workers, job_name="stirring")

    assert len(bucket) == len(workers)
    assert bucket[0].body is None
    assert bucket[0].method == "PATCH"

    for request, worker in zip(bucket, workers):
        assert request.url == f"http://{worker}.local:4999/unit_api/jobs/stop"
        assert request.params == {"job_name": "stirring"}


def test_empty_ClusterJobManager() -> None:
    workers = tuple()  # type: ignore
    with capture_requests() as bucket:
        with ClusterJobManager() as cm:
            cm.kill_jobs(workers, job_name="stirring")

    assert len(bucket) == len(workers)


def test_upsert_setting_insert(job_manager, job_id) -> None:
    # Test inserting a new setting-value pair for a job
    setting = "setting1"
    value1 = "value1"

    # Call the upsert_setting function
    job_manager.upsert_setting(job_id, setting, value1)

    # Verify the setting was inserted correctly
    job_manager.cursor.execute(
        "SELECT value FROM pio_job_published_settings WHERE job_id=? AND setting=?", (job_id, setting)
    )
    result = job_manager.cursor.fetchone()
    assert result is not None
    assert result[0] == value1

    # Call the upsert_setting function
    value2 = "value2"
    job_manager.upsert_setting(job_id, setting, value2)
    # Verify the setting was updated
    job_manager.cursor.execute(
        "SELECT value FROM pio_job_published_settings WHERE job_id=? AND setting=?",
        (job_id, setting),
    )
    result = job_manager.cursor.fetchone()
    assert result is not None
    assert result[0] == value2


def test_upsert_setting_insert_complex_types(job_manager, job_id) -> None:
    setting = "settingDict"
    value = {"A": 1, "B": {"C": 2}}

    # Call the upsert_setting function
    job_manager.upsert_setting(job_id, setting, value)

    # Verify the setting was inserted correctly
    job_manager.cursor.execute(
        "SELECT value FROM pio_job_published_settings WHERE job_id=? AND setting=?", (job_id, setting)
    )
    result = job_manager.cursor.fetchone()
    assert result is not None
    assert result[0] == dumps(value).decode() == r'{"A":1,"B":{"C":2}}'


def test_upsert_setting_update(job_manager, job_id) -> None:
    # First insert a setting-value pair
    setting = "setting1"
    initial_value = "initial_value"
    job_manager.upsert_setting(job_id, setting, initial_value)

    # Now update the setting with a new value
    updated_value = "updated_value"
    job_manager.upsert_setting(job_id, setting, updated_value)

    # Verify the setting was updated
    job_manager.cursor.execute(
        "SELECT value FROM pio_job_published_settings WHERE job_id=? AND setting=?", (job_id, setting)
    )
    result = job_manager.cursor.fetchone()
    assert result is not None
    assert result[0] == updated_value


def test_retrieve_setting(job_manager, job_id) -> None:
    job_key = job_manager.register_and_set_running(
        "test_unit", "test_experiment", "test_name", "test_source", 12345, "test_leader", False
    )

    setting = "my_setting_str"
    initial_value_str = "initial_value"
    job_manager.upsert_setting(job_key, setting, initial_value_str)
    assert job_manager.get_setting_from_running_job("test_name", "my_setting_str") == initial_value_str

    setting = "my_setting_int"
    initial_value_int = 1
    job_manager.upsert_setting(job_key, setting, initial_value_int)
    assert job_manager.get_setting_from_running_job("test_name", "my_setting_int") == initial_value_int

    # turn off
    job_manager.set_not_running(job_key)
    with pytest.raises(NameError):
        job_manager.get_setting_from_running_job("test_name", "my_setting_int")


def test_argextrema_with_empty_lists() -> None:
    with pytest.raises(ValueError):
        argextrema([])
