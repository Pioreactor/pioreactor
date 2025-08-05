# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import pytest
from pioreactorui.config import huey

from .conftest import capture_requests

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

huey.immediate = True


def test_latest_experiment_endpoint(client):
    response = client.get("/api/experiments/latest")

    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp3"
    assert data["description"] == "Third experiment"
    assert data["delta_hours"] > 0


def test_assignment_count(client):
    response = client.get("/api/experiments/assignment_count")

    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 3
    assert data[0]["worker_count"] == 2
    assert data[0]["experiment"] == "exp1"


def test_get_workers(client):
    response = client.get("/api/workers")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 4  # We have 4 workers in the sample data
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit1" in units
    assert "unit2" in units
    assert "unit3" in units
    assert "unit4" in units


def test_get_worker(client):
    response = client.get("/api/workers/unit1")
    assert response.status_code == 200
    data = response.get_json()
    assert data["pioreactor_unit"] == "unit1"
    assert data["is_active"] == 1
    assert data["added_at"] == "2023-10-01T10:00:00Z"


def test_get_experiment_assignment_for_worker(client):
    response = client.get("/api/workers/unit1/experiment")
    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp1"


def test_get_workers_for_experiment(client):
    response = client.get("/api/experiments/exp1/workers")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # exp1 has two workers assigned
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit1" in units
    assert "unit2" in units


def test_add_worker_to_experiment(client):
    # Add unit4 to exp1
    response = client.put("/api/experiments/exp1/workers", json={"pioreactor_unit": "unit4"})
    assert response.status_code == 200

    # Verify unit4 is now assigned to exp1
    response = client.get("/api/experiments/exp1/workers")
    data = response.get_json()
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit4" in units


def test_remove_worker_from_experiment(client):
    # Remove unit2 from exp1
    response = client.delete("/api/experiments/exp1/workers/unit2")
    assert response.status_code == 200

    # Verify unit2 is no longer assigned to exp1
    response = client.get("/api/experiments/exp1/workers")
    data = response.get_json()
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit2" not in units


def test_remove_worker_from_experiment_it_doesnt_belong_to(client):
    # Try to remove unit2 from an experiment it's not assigned to.
    response = client.delete("/api/experiments/exp99/workers/unit2")
    assert response.status_code == 404


def test_get_assignment_count(client):
    response = client.get("/api/experiments/assignment_count")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 3  # We have 3 experiments
    exp1 = next((item for item in data if item["experiment"] == "exp1"), None)
    exp2 = next((item for item in data if item["experiment"] == "exp2"), None)
    exp3 = next((item for item in data if item["experiment"] == "exp3"), None)
    assert exp1["worker_count"] == 2
    assert exp2["worker_count"] == 1
    assert exp3["worker_count"] == 1


def test_change_worker_status(client):
    # Deactivate unit3
    response = client.put("/api/workers/unit3/is_active", json={"is_active": 0})
    assert response.status_code == 200

    # Verify the status change
    response = client.get("/api/workers/unit3")
    data = response.get_json()
    assert data["is_active"] == 0


def test_get_unit_labels(client):
    response = client.get("/api/experiments/exp1/unit_labels")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # exp1 has labels for unit1 and unit2
    assert data["unit1"] == "Reactor 1"
    assert data["unit2"] == "Reactor 2"


def test_upsert_unit_labels(client):
    # Update label for unit1 in exp1
    response = client.patch(
        "/api/experiments/exp1/unit_labels",
        json={"unit": "unit1", "label": "Updated Reactor 1"},
    )
    assert response.status_code == 201

    # Verify the label update
    response = client.get("/api/experiments/exp1/unit_labels")
    data = response.get_json()
    assert data["unit1"] == "Updated Reactor 1"


@pytest.mark.xfail(reason="need to mock datetime")
def test_get_logs_for_unit_and_experiment(client):
    response = client.get("/api/workers/unit1/experiments/exp1/logs")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1  # Only one log entry for unit1 in exp1
    log = data[0]
    assert log["message"] == "Started mixing"
    assert log["source"] == "mixer"
    assert log["level"] == "INFO"
    assert log["task"] == "mixing_task"


@pytest.mark.xfail(reason="need to mock datetime")
def test_get_growth_rates(client):
    response = client.get("/api/experiments/exp1/time_series/growth_rates")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # Two growth rates for exp1
    rates = [item["rate"] for item in data]
    assert 0.02 in rates
    assert 0.025 in rates


def test_create_experiment(client):
    # Create a new experiment
    response = client.post(
        "/api/experiments",
        json={
            "experiment": "exp4",
            "created_at": "2023-10-04T12:00:00Z",
            "description": "Fourth experiment",
            "media_used": "Special media",
            "organism_used": "Algae",
        },
    )
    assert response.status_code == 201  # Created

    # Verify the experiment exists
    response = client.get("/api/experiments/exp4")
    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp4"
    assert data["description"] == "Fourth experiment"


def test_create_duplicate_experiment(client):
    # Try to create an experiment with a duplicate name 'exp1'
    response = client.post(
        "/api/experiments",
        json={
            "experiment": "exp1",
            "created_at": "2023-10-05T12:00:00Z",
            "description": "Duplicate experiment",
        },
    )
    assert response.status_code == 409


def test_update_experiment(client):
    # Update an existing experiment
    response = client.patch(
        "/api/experiments/exp2",
        json={
            "description": "Updated second experiment",
        },
    )
    assert response.status_code == 200  # OK

    # Verify the updates
    response = client.get("/api/experiments/exp2")
    data = response.get_json()
    assert data["description"] == "Updated second experiment"


def test_update_nonexistent_experiment(client):
    # Try to update an experiment that doesn't exist
    response = client.patch(
        "/api/experiments/nonexistent_exp",
        json={
            "description": "This should fail",
        },
    )
    assert response.status_code == 404  # Not Found


def test_create_experiment_missing_fields(client):
    # Try to create an experiment without required fields
    response = client.post(
        "/api/experiments",
        json={
            # Missing 'experiment' name
            "created_at": "2023-10-06T12:00:00Z",
            "description": "No name experiment",
        },
    )
    assert response.status_code == 400  # Bad Request


def test_404_for_unknown_api(client):
    response = client.get("/api/this-doesnt-exist")
    assert response.status_code == 404

    response = client.get("/unit_api/this-doesnt-exist")
    assert response.status_code == 404

    response = client.get("/this-doesnt-exist")
    assert response.status_code == 404


def test_broadcasting(client):
    response = client.get("/api/workers")
    data = response.get_json()
    count_of_workers = len(data)

    with capture_requests() as bucket:
        response = client.get("/api/units/$broadcast/versions/ui")

    assert len(bucket) == count_of_workers


def test_broadcast_in_manage_all(client):
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/$broadcast/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 2
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"
    from pioreactor.models import get_current_model

    m = get_current_model()
    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "MODEL_NAME": m.model_name,
            "MODEL_VERSION": m.model_version,
        },
    }

    # Remove unit2 from exp1
    client.delete("/api/experiments/exp1/workers/unit2")

    with capture_requests() as bucket:
        client.post("/api/workers/$broadcast/jobs/run/job_name/stirring/experiments/exp1", json={})
    assert len(bucket) == 1


def test_run_job(client):
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 1
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"
    from pioreactor.models import get_current_model

    m = get_current_model()
    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "MODEL_NAME": m.model_name,
            "MODEL_VERSION": m.model_version,
        },
    }

    # wrong experiment!
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp99",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 0

    # not active!
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit4/jobs/run/job_name/stirring/experiments/exp3",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 0


def test_run_job_with_job_source(client):
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}, "env": {"JOB_SOURCE": "experiment_profile"}},
        )
    assert len(bucket) == 1
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"
    from pioreactor.models import get_current_model

    m = get_current_model()
    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "JOB_SOURCE": "experiment_profile",
            "MODEL_NAME": m.model_name,
            "MODEL_VERSION": m.model_version,
        },
    }


def test_run_job_response(client):
    # regression test
    run_post_response = client.post(
        "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
        json={"options": {"target_rpm": 10}},
    )
    assert run_post_response.status_code == 202
    task_data = run_post_response.get_json()

    multicast_task_query_response = client.get(task_data["result_url_path"])
    assert multicast_task_query_response.status_code == 200
    multicast_task_data = multicast_task_query_response.get_json()
    assert multicast_task_data["status"] == "complete"


@pytest.mark.skipif(IN_GITHUB_ACTIONS, reason="Requires a webserver running to handle huey pings.")
def test_get_settings_unit_api(client):
    from pioreactor.background_jobs.stirring import start_stirring

    with start_stirring():
        r = client.get(
            "/unit_api/jobs/settings/job_name/stirring",
        )
        assert r.json["settings"]["$state"] == "ready"
        assert r.json["settings"]["target_rpm"] == 500.0

        r = client.get(
            "/unit_api/jobs/settings/job_name/stirring/setting/target_rpm",
        )
        r.json["target_rpm"] == "500.0"


@pytest.mark.skipif(IN_GITHUB_ACTIONS, reason="Requires a webserver running to handle huey pings.")
def test_get_settings_api(client):
    from pioreactor.background_jobs.stirring import start_stirring

    with start_stirring(unit="unit1", experiment="exp1"):
        r = client.get(
            "/api/experiments/exp1/jobs/settings/job_name/stirring",
        )
        # follow the task
        r = client.get(r.json["result_url_path"])
        settings_per_unit = r.json["result"]
        assert settings_per_unit["unit2"] is None
        assert settings_per_unit["unit1"]["settings"]["target_rpm"] == 500.0

        # next api
        r = client.get("/api/workers/unit1/jobs/settings/job_name/stirring")
        # follow the task
        r = client.get(r.json["result_url_path"])
        settings_per_unit = r.json["result"]
        assert settings_per_unit["unit1"]["settings"]["target_rpm"] == 500.0
