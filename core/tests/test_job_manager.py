# -*- coding: utf-8 -*-
import time
from datetime import datetime

import pytest
from msgspec.json import encode as dumps
from pioreactor.utils.job_manager import ClusterJobManager
from pioreactor.utils.job_manager import JobManager
from pioreactor.utils.job_manager import JobMetadataKey
from tests.conftest import capture_requests


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

    for request, worker in zip(sorted(bucket, key=lambda item: item.url), sorted(workers)):
        assert request.url == f"http://{worker}.local:4999/unit_api/jobs/stop"
        assert request.json == {"job_name": "stirring"}


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
        "SELECT value, created_at, updated_at FROM pio_job_published_settings WHERE job_id=? AND setting=?",
        (job_id, setting),
    )
    result = job_manager.cursor.fetchone()
    assert result is not None
    stored_value, created_at, updated_at = result
    assert stored_value == value1
    assert created_at is not None
    assert updated_at is not None

    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    assert created_dt <= updated_dt

    # Call the upsert_setting function
    value2 = "value2"
    job_manager.upsert_setting(job_id, setting, value2)
    # Verify the setting was updated
    job_manager.cursor.execute(
        "SELECT value, created_at, updated_at FROM pio_job_published_settings WHERE job_id=? AND setting=?",
        (job_id, setting),
    )
    result = job_manager.cursor.fetchone()
    assert result is not None
    stored_value, created_at_after, updated_at_after = result
    assert stored_value == value2
    assert created_at_after == created_at
    updated_dt_after = datetime.fromisoformat(updated_at_after.replace("Z", "+00:00"))
    assert updated_dt <= updated_dt_after


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
    job_manager.cursor.execute(
        "SELECT value, created_at, updated_at FROM pio_job_published_settings WHERE job_id=? AND setting=?",
        (job_id, setting),
    )
    before_update = job_manager.cursor.fetchone()
    assert before_update is not None
    _, created_at_before, updated_at_before = before_update
    created_dt_before = datetime.fromisoformat(created_at_before.replace("Z", "+00:00"))
    updated_dt_before = datetime.fromisoformat(updated_at_before.replace("Z", "+00:00"))
    assert created_dt_before <= updated_dt_before

    # Now update the setting with a new value
    updated_value = "updated_value"
    time.sleep(0.01)
    job_manager.upsert_setting(job_id, setting, updated_value)

    # Verify the setting was updated
    job_manager.cursor.execute(
        "SELECT value, created_at, updated_at FROM pio_job_published_settings WHERE job_id=? AND setting=?",
        (job_id, setting),
    )
    result = job_manager.cursor.fetchone()
    assert result is not None
    stored_value, created_at_after, updated_at_after = result
    assert stored_value == updated_value
    assert created_at_after == created_at_before
    updated_dt_after = datetime.fromisoformat(updated_at_after.replace("Z", "+00:00"))
    assert updated_dt_before < updated_dt_after


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
