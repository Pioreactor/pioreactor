# -*- coding: utf-8 -*-
import os
from datetime import datetime
from datetime import UTC
from io import BytesIO
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from pioreactor.web.config import huey
from pytest import MonkeyPatch
from tests.utils import FakeMQTTClient
from tests.utils import FakeMQTTMessageInfo

from .conftest import capture_requests
from .test_unit_api import _build_valid_calibration_yaml

IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

huey.immediate = True


def test_process_delayed_json_response_accepts_created_status() -> None:
    import pioreactor.web.tasks as mod

    class DummyResponse:
        status_code = 201

        def json(self) -> dict[str, str]:
            return {"msg": "Calibration created successfully."}

    assert mod._process_delayed_json_response("unit1", DummyResponse()) == (
        "unit1",
        {"msg": "Calibration created successfully."},
    )


def test_latest_experiment_endpoint(client) -> None:
    response = client.get("/api/experiments/latest")

    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp3"
    assert data["description"] == "Third experiment"
    assert data["delta_hours"] > 0
    assert data["worker_count"] == 1
    assert data["tags"] == ["archive", "fermentation", "priority"]


def test_assignment_count(client) -> None:
    response = client.get("/api/experiments/assignment_count")

    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 3
    assert data[0]["worker_count"] == 2
    assert data[0]["experiment"] == "exp1"


def test_get_workers(client) -> None:
    response = client.get("/api/workers")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 4  # We have 4 workers in the sample data
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit1" in units
    assert "unit2" in units
    assert "unit3" in units
    assert "unit4" in units


def test_discover_workers_endpoint(client, monkeypatch) -> None:
    # Mock network discovery to yield an existing and a new worker
    monkeypatch.setattr(
        "pioreactor.utils.networking.discover_workers_on_network",
        lambda terminate: iter(["unit1", "new_unit"]),
    )
    response = client.get("/api/workers/discover")
    assert response.status_code == 200
    data = response.get_json()
    units = [w["pioreactor_unit"] for w in data]
    assert "new_unit" in units
    assert "unit1" not in units


def test_get_worker(client) -> None:
    response = client.get("/api/workers/unit1")
    assert response.status_code == 200
    data = response.get_json()
    assert data["pioreactor_unit"] == "unit1"
    assert data["is_active"] == 1
    assert data["added_at"] == "2023-10-01T10:00:00Z"


def test_get_experiment_assignment_for_worker(client) -> None:
    response = client.get("/api/workers/unit1/experiment")
    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp1"


def test_get_workers_for_experiment(client) -> None:
    response = client.get("/api/experiments/exp1/workers")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # exp1 has two workers assigned
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit1" in units
    assert "unit2" in units


def test_add_worker_to_experiment(client) -> None:
    # Add unit4 to exp1
    response = client.put("/api/experiments/exp1/workers", json={"pioreactor_unit": "unit4"})
    assert response.status_code == 200

    # Verify unit4 is now assigned to exp1
    response = client.get("/api/experiments/exp1/workers")
    data = response.get_json()
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit4" in units


def test_reassign_worker_to_experiment_stops_jobs_from_previous_experiment(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_multicast_post(
        endpoint: str,
        units: list[str],
        json: dict[str, object] | list[dict[str, object] | None] | None = None,
        **_kwargs,
    ) -> dict[str, object]:
        captured["endpoint"] = endpoint
        captured["units"] = units
        captured["json"] = json
        return {}

    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_post", fake_multicast_post)

    response = client.put("/api/experiments/exp2/workers", json={"pioreactor_unit": "unit2"})
    assert response.status_code == 200

    assert captured["endpoint"] == "/unit_api/jobs/stop"
    assert captured["units"] == ["unit2"]
    assert captured["json"] == {"experiment": "exp1"}

    response = client.get("/api/workers/unit2/experiment")
    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp2"


def test_remove_worker_from_experiment(client) -> None:
    # Remove unit2 from exp1
    response = client.delete("/api/experiments/exp1/workers/unit2")
    assert response.status_code == 200

    # Verify unit2 is no longer assigned to exp1
    response = client.get("/api/experiments/exp1/workers")
    data = response.get_json()
    units = [worker["pioreactor_unit"] for worker in data]
    assert "unit2" not in units


def test_remove_worker_from_experiment_it_doesnt_belong_to(client) -> None:
    # Try to remove unit2 from an experiment it's not assigned to.
    response = client.delete("/api/experiments/exp99/workers/unit2")
    assert response.status_code == 404


def test_get_assignment_count(client) -> None:
    response = client.get("/api/experiments/assignment_count")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 3  # We have 3 experiments
    exp1 = next((item for item in data if item["experiment"] == "exp1"))
    exp2 = next((item for item in data if item["experiment"] == "exp2"))
    exp3 = next((item for item in data if item["experiment"] == "exp3"))
    assert exp1["worker_count"] == 2
    assert exp2["worker_count"] == 1
    assert exp3["worker_count"] == 1


def test_change_worker_status(client) -> None:
    # Deactivate unit3
    response = client.put("/api/workers/unit3/is_active", json={"is_active": 0})
    assert response.status_code == 200

    # Verify the status change
    response = client.get("/api/workers/unit3")
    data = response.get_json()
    assert data["is_active"] == 0


def test_change_worker_model_triggers_hardware_check_for_v1_5(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post_into_unit(unit: str, endpoint: str, json: dict | None = None) -> None:
        captured["unit"] = unit
        captured["endpoint"] = endpoint
        captured["json"] = json

    monkeypatch.setattr("pioreactor.web.api.tasks.post_into_unit", fake_post_into_unit)

    response = client.put(
        "/api/workers/unit1/model",
        json={"model_name": "pioreactor_20ml", "model_version": "1.5"},
    )
    assert response.status_code == 200
    assert captured["unit"] == "unit1"
    assert captured["endpoint"] == "/unit_api/hardware/check"
    assert captured["json"] == {"model_name": "pioreactor_20ml", "model_version": "1.5"}


def test_change_worker_model_does_not_trigger_hardware_check_for_non_v1_5(client, monkeypatch) -> None:
    def fake_post_into_unit(*_args, **_kwargs) -> None:
        raise AssertionError("hardware check should not be triggered")

    monkeypatch.setattr("pioreactor.web.api.tasks.post_into_unit", fake_post_into_unit)

    response = client.put(
        "/api/workers/unit1/model",
        json={"model_name": "pioreactor_20ml", "model_version": "1.1"},
    )
    assert response.status_code == 200


def test_get_unit_labels(client) -> None:
    response = client.get("/api/experiments/exp1/unit_labels")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # exp1 has labels for unit1 and unit2
    assert data["unit1"] == "Reactor 1"
    assert data["unit2"] == "Reactor 2"


def test_upsert_unit_labels(client) -> None:
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
def test_get_logs_for_unit_and_experiment(client) -> None:
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
def test_get_growth_rates(client) -> None:
    response = client.get("/api/experiments/exp1/time_series/growth_rates")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2  # Two growth rates for exp1
    rates = [item["rate"] for item in data]
    assert 0.02 in rates
    assert 0.025 in rates


def test_get_system_logs_filters_universal_experiment(client) -> None:
    from pioreactor.web.app import modify_app_db
    from pioreactor.whoami import UNIVERSAL_EXPERIMENT

    modify_app_db(
        "INSERT INTO logs (experiment, pioreactor_unit, timestamp, message, source, level, task) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            UNIVERSAL_EXPERIMENT,
            "unit1",
            "2023-10-04T12:00:00Z",
            "System event logged",
            "system",
            "INFO",
            "system",
        ),
    )

    response = client.get("/api/units/unit1/system_logs")
    assert response.status_code == 200
    data = response.get_json()
    assert any(row["message"] == "System event logged" for row in data)
    assert all(row["experiment"] == UNIVERSAL_EXPERIMENT for row in data)


def test_get_recent_logs_excludes_universal_experiment(client) -> None:
    from pioreactor.web.app import modify_app_db
    from pioreactor.whoami import UNIVERSAL_EXPERIMENT

    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    modify_app_db(
        "INSERT INTO logs (experiment, pioreactor_unit, timestamp, message, source, level, task) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "exp1",
            "unit1",
            now,
            "Experiment-only event",
            "app",
            "INFO",
            "app",
        ),
    )
    modify_app_db(
        "INSERT INTO logs (experiment, pioreactor_unit, timestamp, message, source, level, task) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            UNIVERSAL_EXPERIMENT,
            "unit1",
            now,
            "Universal event",
            "app",
            "INFO",
            "app",
        ),
    )

    response = client.get("/api/experiments/exp1/recent_logs")
    assert response.status_code == 200
    data = response.get_json()

    assert any(row["message"] == "Experiment-only event" for row in data)
    assert all(row["message"] != "Universal event" for row in data)
    assert all(row["experiment"] == "exp1" for row in data)


@pytest.mark.parametrize(
    "path",
    [
        "/api/experiments/exp1/time_series/temperature_readings",
        "/api/workers/unit1/experiments/exp1/time_series/temperature_readings",
    ],
)
def test_time_series_target_points_validation_returns_400(client, path: str) -> None:
    response = client.get(f"{path}?target_points=0")
    assert response.status_code == 400


def test_create_experiment(client) -> None:
    # Create a new experiment
    response = client.post(
        "/api/experiments",
        json={
            "experiment": "exp4",
            "created_at": "2023-10-04T12:00:00Z",
            "description": "Fourth experiment",
            "media_used": "Special media",
            "organism_used": "Algae",
            "tags": ["seed", "project-x", "seed"],
        },
    )
    assert response.status_code == 201  # Created
    data = response.get_json()
    assert data["tags"] == ["seed", "project-x"]

    # Verify the experiment exists
    response = client.get("/api/experiments/exp4")
    assert response.status_code == 200
    data = response.get_json()
    assert data["experiment"] == "exp4"
    assert data["description"] == "Fourth experiment"
    assert data["tags"] == ["seed", "project-x"]
    assert data["worker_count"] == 0


def test_create_duplicate_experiment(client) -> None:
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


def test_update_experiment(client) -> None:
    # Update an existing experiment
    response = client.patch(
        "/api/experiments/exp2",
        json={
            "description": "Updated second experiment",
            "tags": ["project-beta", "  follow-up ", "PROJECT-BETA", ""],
        },
    )
    assert response.status_code == 200  # OK
    data = response.get_json()
    assert data["tags"] == ["project-beta", "follow-up"]

    # Verify the updates
    response = client.get("/api/experiments/exp2")
    data = response.get_json()
    assert data["description"] == "Updated second experiment"
    assert data["tags"] == ["project-beta", "follow-up"]


def test_get_experiments_includes_tags_and_worker_count(client) -> None:
    response = client.get("/api/experiments")

    assert response.status_code == 200
    data = response.get_json()
    exp3 = next(item for item in data if item["experiment"] == "exp3")
    exp0 = next(item for item in data if item["experiment"] == "exp0")
    assert exp3["worker_count"] == 1
    assert exp3["tags"] == ["archive", "fermentation", "priority"]
    assert exp0["worker_count"] == 0
    assert exp0["tags"] == []


def test_update_experiment_tags_only(client) -> None:
    response = client.patch(
        "/api/experiments/exp1",
        json={
            "tags": ["RNA", "screening", "rna", "scale-up"],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["description"] == "First experiment"
    assert data["tags"] == ["RNA", "screening", "scale-up"]


def test_update_nonexistent_experiment(client) -> None:
    # Try to update an experiment that doesn't exist
    response = client.patch(
        "/api/experiments/nonexistent_exp",
        json={
            "description": "This should fail",
        },
    )
    assert response.status_code == 404  # Not Found


def test_update_experiment_with_invalid_tags_payload(client) -> None:
    response = client.patch(
        "/api/experiments/exp1",
        json={
            "tags": "project-a",
        },
    )

    assert response.status_code == 400


def test_create_experiment_missing_fields(client) -> None:
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


def test_404_for_unknown_api(client) -> None:
    response = client.get("/api/this-doesnt-exist")
    assert response.status_code == 404

    response = client.get("/unit_api/this-doesnt-exist")
    assert response.status_code == 404

    response = client.get("/this-doesnt-exist")
    assert response.status_code == 404


def test_removed_config_files_api_returns_404(client) -> None:
    response = client.get("/api/config/files/not-a-config.txt")
    assert response.status_code == 404


def test_get_config_for_broadcast_uses_worker_merged_config(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    from pioreactor.web.app import HOSTNAME

    dot_pioreactor = tmp_path / ".pioreactor"
    dot_pioreactor.mkdir()
    (dot_pioreactor / "config.ini").write_text(
        "[cluster.topology]\nleader_hostname=leader\nleader_address=leader.local\n[mqtt]\nbroker_address=leader.local\n[shared]\nvalue=global\n",
        encoding="utf-8",
    )
    (dot_pioreactor / "unit_config.ini").write_text("[shared]\nvalue=leader\n", encoding="utf-8")

    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    monkeypatch.setattr("pioreactor.web.api.get_all_units", lambda: [HOSTNAME, "unit1", "unit2"])
    monkeypatch.setattr(
        "pioreactor.web.cache.multicast_get_with_leader_cache",
        lambda *_args, **_kwargs: {
            "unit1": {"shared": {"value": "unit1"}},
            "unit2": {"shared": {"value": "unit2"}},
        },
    )
    response = client.get("/api/config/units/$broadcast")
    assert response.status_code == 200

    data = response.get_json()
    assert data[HOSTNAME]["shared"]["value"] == "leader"
    assert data["unit1"]["shared"]["value"] == "unit1"
    assert data["unit2"]["shared"]["value"] == "unit2"


def test_unit_api_specific_config_round_trip(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    dot_pioreactor.mkdir()
    (dot_pioreactor / "config.ini").write_text(
        "[cluster.topology]\nleader_hostname=leader\nleader_address=leader.local\n[mqtt]\nbroker_address=leader.local\n[shared]\nvalue=global\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))

    response = client.get("/unit_api/config/specific")
    assert response.status_code == 200
    assert response.data.decode("utf-8") == ""

    response = client.patch("/unit_api/config/specific", json={"code": "[shared]\nvalue=unit-local\n"})
    assert response.status_code == 200

    response = client.get("/unit_api/config/specific")
    assert response.status_code == 200
    assert response.data.decode("utf-8") == "[shared]\nvalue=unit-local\n"

    response = client.get("/unit_api/config/merged")
    assert response.status_code == 200
    assert response.get_json()["shared"]["value"] == "unit-local"


def test_update_specific_config_for_worker_saves_snapshot(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(
        mod,
        "post_into",
        lambda *_args, **_kwargs: MureqResponse(
            "http://unit1.local:4999/unit_api/config/specific",
            200,
            {"Content-Type": "application/json"},
            b'{"status":"success"}',
        ),
    )

    response = client.patch("/api/config/units/unit1/specific", json={"code": "[section]\nvalue=1\n"})
    assert response.status_code == 200

    history_response = client.get("/api/config/units/unit1/specific/history")
    assert history_response.status_code == 200
    history = history_response.get_json()
    assert history[0]["filename"] == "unit_config.ini::unit1"
    assert history[0]["data"] == "[section]\nvalue=1\n"


def test_update_specific_config_for_worker_propagates_validation_error(
    client: FlaskClient, monkeypatch: MonkeyPatch
) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")
    monkeypatch.setattr(
        mod,
        "post_into",
        lambda *_args, **_kwargs: MureqResponse(
            "http://unit1.local:4999/unit_api/config/specific",
            400,
            {"Content-Type": "application/json"},
            b'{"error":"Incorrect syntax. Please fix and try again."}',
        ),
    )

    response = client.patch("/api/config/units/unit1/specific", json={"code": "[broken"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Incorrect syntax. Please fix and try again."


def test_create_experiment_profile_invalid_filename_returns_400(client) -> None:
    response = client.post(
        "/api/experiment_profiles",
        json={"body": "experiment_profile_name: demo", "filename": "bad?name.yaml"},
    )
    assert response.status_code == 400


def test_update_experiment_profile_invalid_filename_returns_400(client) -> None:
    response = client.patch(
        "/api/experiment_profiles/bad:name.yaml",
        json={"body": "experiment_profile_name: demo"},
    )
    assert response.status_code == 400


def test_create_experiment_profile_returns_diagnostics_for_semantic_validation_errors(client) -> None:
    response = client.post(
        "/api/experiment_profiles",
        json={
            "body": """
experiment_profile_name: demo
common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 1.0
          t: 1h
""",
            "filename": "validator_semantic_error_test.yaml",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Validation error."
    assert payload["diagnostics"][0]["code"] == "action.time.conflict"
    assert payload["diagnostics"][0]["path"] == "common.jobs.stirring.actions[0]"


def test_broadcasting(client) -> None:
    response = client.get("/api/workers")
    data = response.get_json()
    count_of_workers = len(data)

    with capture_requests() as bucket:
        response = client.get("/api/units/$broadcast/versions/app")

    assert len(bucket) == (count_of_workers + 1)  # leader is localhost, whos not a worker in this fixture


def test_broadcast_in_manage_all(client) -> None:
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/$broadcast/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 2
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"

    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "MODEL_NAME": "pioreactor_20ml",
            "MODEL_VERSION": "1.1",
            "HOSTNAME": "unit1",
            "TESTING": "1",
            "DOT_PIOREACTOR": os.environ["DOT_PIOREACTOR"],
        },
    }

    # Remove unit2 from exp1
    client.delete("/api/experiments/exp1/workers/unit2")

    with capture_requests() as bucket:
        client.post("/api/workers/$broadcast/jobs/run/job_name/stirring/experiments/exp1", json={})
    assert len(bucket) == 1


def test_run_job(client) -> None:
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}},
        )
    assert len(bucket) == 1
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"

    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "MODEL_NAME": "pioreactor_20ml",
            "MODEL_VERSION": "1.1",
            "HOSTNAME": "unit1",
            "TESTING": "1",
            "DOT_PIOREACTOR": os.environ["DOT_PIOREACTOR"],
        },
    }

    # stop job now
    client.post(
        "/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1",
    )

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


def test_run_job_with_job_source(client) -> None:
    # regression test
    with capture_requests() as bucket:
        client.post(
            "/api/workers/unit1/jobs/run/job_name/stirring/experiments/exp1",
            json={"options": {"target_rpm": 10}, "env": {"JOB_SOURCE": "experiment_profile"}},
        )
    assert len(bucket) == 1
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"

    assert bucket[0].json == {
        "args": [],
        "options": {"target_rpm": 10},
        "config_overrides": [],
        "env": {
            "EXPERIMENT": "exp1",
            "ACTIVE": "1",
            "JOB_SOURCE": "experiment_profile",
            "MODEL_NAME": "pioreactor_20ml",
            "MODEL_VERSION": "1.1",
            "HOSTNAME": "unit1",
            "TESTING": "1",
            "DOT_PIOREACTOR": os.environ["DOT_PIOREACTOR"],
        },
    }

    # stop job now
    client.post(
        "/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1",
    )


@pytest.mark.slow
def test_run_job_response(client) -> None:
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
    assert multicast_task_data["status"] == "succeeded"

    # stop job now
    client.post(
        "/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1",
    )


def test_stop_specific_job_returns_task_response_when_mqtt_publish_fails(client, monkeypatch) -> None:
    import pioreactor.web.api as mod

    class DummyTask:
        id = "fallback-task"

    monkeypatch.setattr(
        mod,
        "create_client",
        lambda *_args, **_kwargs: FakeMQTTClient(
            message_info_factory=lambda: FakeMQTTMessageInfo(wait_error=RuntimeError("mqtt down"))
        ),
    )
    monkeypatch.setattr(mod.tasks, "multicast_post", lambda *_args, **_kwargs: DummyTask())

    response = client.post("/api/workers/unit1/jobs/stop/job_name/stirring/experiments/exp1")

    assert response.status_code == 202
    data = response.get_json()
    assert data["task_id"] == "fallback-task"
    assert data["result_url_path"] == "/unit_api/task_results/fallback-task"


@pytest.mark.skipif(IN_GITHUB_ACTIONS, reason="Requires a webserver running to handle huey pings.")
def test_get_settings_unit_api(client) -> None:
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


@pytest.mark.slow
@pytest.mark.skipif(IN_GITHUB_ACTIONS, reason="Requires a webserver running to handle huey pings.")
def test_get_settings_api(client) -> None:
    from pioreactor.background_jobs.stirring import start_stirring

    with start_stirring(unit="unit1", experiment="exp1"):
        r = client.get("/api/workers/$broadcast/jobs/settings/job_name/stirring/experiments/exp1")
        # follow the task
        r = client.get(r.json["result_url_path"])
        settings_per_unit = r.json["result"]
        assert settings_per_unit["unit2"] is None
        assert settings_per_unit["unit1"]["settings"]["target_rpm"] == 500.0

        # next api
        r = client.get("/api/workers/unit1/jobs/settings/job_name/stirring/experiments/exp1")
        # follow the task
        r = client.get(r.json["result_url_path"])
        settings_per_unit = r.json["result"]
        assert settings_per_unit["unit1"]["settings"]["target_rpm"] == 500.0


def test_get_bioreactor_descriptors(client) -> None:
    response = client.get("/api/bioreactor/descriptors")

    assert response.status_code == 200
    data = response.get_json()
    assert [descriptor["key"] for descriptor in data] == [
        "current_volume_ml",
        "efflux_tube_volume_ml",
        "alt_media_fraction",
    ]


def test_get_job_descriptors_for_worker_proxies_unit_api(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    def fake_get_from(*_args, **_kwargs) -> MureqResponse:
        return MureqResponse(
            "http://unit1.local:4999/unit_api/jobs/descriptors",
            200,
            {"Content-Type": "application/json"},
            b'[{"job_name":"worker_plugin","display_name":"Worker plugin","display":true,"published_settings":[]}]',
        )

    monkeypatch.setattr(mod, "get_from", fake_get_from)
    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")

    response = client.get("/api/workers/unit1/jobs/descriptors")

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "job_name": "worker_plugin",
            "display_name": "Worker plugin",
            "display": True,
            "published_settings": [],
        }
    ]


def test_get_job_descriptors_for_worker_rejects_broadcast(client) -> None:
    response = client.get("/api/workers/$broadcast/jobs/descriptors")

    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "Cannot fetch job descriptors with $broadcast; choose a specific Pioreactor."


def test_get_automation_descriptors_for_worker_proxies_unit_api(client, monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.api as mod
    from pioreactor.mureq import Response as MureqResponse

    def fake_get_from(*_args, **_kwargs) -> MureqResponse:
        return MureqResponse(
            "http://unit1.local:4999/unit_api/automations/descriptors/dosing",
            200,
            {"Content-Type": "application/json"},
            b'[{"automation_name":"worker_automation","display_name":"Worker automation","description":"Worker-only automation","fields":[]}]',
        )

    monkeypatch.setattr(mod, "get_from", fake_get_from)
    monkeypatch.setattr(mod, "resolve_to_address", lambda unit: f"{unit}.local")

    response = client.get("/api/workers/unit1/automations/descriptors/dosing")

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "automation_name": "worker_automation",
            "display_name": "Worker automation",
            "description": "Worker-only automation",
            "fields": [],
        }
    ]


def test_get_automation_descriptors_for_worker_rejects_broadcast(client) -> None:
    response = client.get("/api/workers/$broadcast/automations/descriptors/dosing")

    assert response.status_code == 400
    data = response.get_json()
    assert (
        data["error"] == "Cannot fetch automation descriptors with $broadcast; choose a specific Pioreactor."
    )


def test_update_bioreactor_on_unit_queues_multicast_patch(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_multicast_patch(endpoint: str, units: list[str], json: dict | None = None) -> str:
        captured["endpoint"] = endpoint
        captured["units"] = units
        captured["json"] = json
        return "task"

    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_patch", fake_multicast_patch)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.patch(
        "/api/workers/unit1/bioreactor/update/experiments/exp1",
        json={"values": {"current_volume_ml": 12.5, "alt_media_fraction": 0.4}},
    )

    assert response.status_code == 202
    assert captured["endpoint"] == "/unit_api/bioreactor/experiments/exp1"
    assert captured["units"] == ["unit1"]
    assert captured["json"] == {"values": {"current_volume_ml": 12.5, "alt_media_fraction": 0.4}}


def test_update_bioreactor_on_unit_old_route_is_not_available(client) -> None:
    response = client.patch(
        "/api/workers/unit1/experiments/exp1/bioreactor",
        json={"values": {"current_volume_ml": 12.5}},
    )

    assert response.status_code == 404


def test_update_next_version_defaults_to_broadcast(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_update_app_across_cluster(units: str = "$broadcast") -> str:
        captured["units"] = units
        return "task"

    monkeypatch.setattr("pioreactor.web.api.tasks.update_app_across_cluster", fake_update_app_across_cluster)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post("/api/system/update_next_version")
    assert response.status_code == 202
    assert captured["units"] == "$broadcast"


def test_update_next_version_accepts_unit_selection(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_update_app_across_cluster(units: str = "$broadcast") -> str:
        captured["units"] = units
        return "task"

    monkeypatch.setattr("pioreactor.web.api.tasks.update_app_across_cluster", fake_update_app_across_cluster)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post("/api/system/update_next_version", json={"units": "unit2"})
    assert response.status_code == 202
    assert captured["units"] == "unit2"


def test_system_upload_uses_unique_staged_temp_archive_name(
    client: FlaskClient, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("pioreactor.web.api.tempfile.gettempdir", lambda: str(tmp_path))

    response = client.post(
        "/api/system/upload",
        data={"file": (BytesIO(b"archive-bytes"), "release_26.4.2.zip")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    save_path = Path(payload["save_path"])

    assert save_path.parent == tmp_path
    assert save_path.name.startswith("pioreactor_update_archive_")
    assert save_path.name.endswith("_release_26.4.2.zip")
    assert save_path.read_bytes() == b"archive-bytes"


def test_multicast_get_with_leader_cache_reuses_cached_unit_payloads(monkeypatch: MonkeyPatch) -> None:
    import pioreactor.web.tasks as mod

    mod.clear_multicast_get_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])

    calls = 0

    def fake_multicast_get_uncached(
        endpoint: str,
        units: list[str],
        json: dict[str, object] | list[dict[str, object] | None] | None = None,
        timeout: float = 5.0,
        return_raw: bool = False,
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        assert endpoint == "/unit_api/calibrations"
        assert units == ["unit1"]
        assert json is None
        assert timeout == 5.0
        assert return_raw is False
        return {"unit1": {"od90": [{"calibration_name": "cached-on-leader"}]}}

    monkeypatch.setattr("pioreactor.web.tasks._multicast_get_uncached", fake_multicast_get_uncached)

    first = mod.multicast_get_with_leader_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])
    second = mod.multicast_get_with_leader_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])

    first_payload = first.get(blocking=True, timeout=1)
    second_payload = second.get(blocking=True, timeout=1)

    assert first_payload == {"unit1": {"od90": [{"calibration_name": "cached-on-leader"}]}}
    assert second_payload == first_payload
    assert calls == 1

    mod.clear_multicast_get_cache("test-calibrations", "/unit_api/calibrations", ["unit1"])


def test_get_all_calibrations_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/calibrations")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "calibrations"
    assert captured["endpoint"] == "/unit_api/calibrations"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_get_calibration_protocols_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/calibration_protocols")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "calibration_protocols"
    assert captured["endpoint"] == "/unit_api/calibration_protocols"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_get_all_active_calibrations_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/active_calibrations")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "active_calibrations"
    assert captured["endpoint"] == "/unit_api/active_calibrations"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_create_calibration_invalidates_cached_worker_payloads(client, monkeypatch: MonkeyPatch) -> None:
    captured_calls: list[tuple[str, str, list[str]]] = []

    def fake_invalidate_multicast_get_cache(targets: list[object], units: list[str]) -> None:
        captured_calls.extend((target.namespace, target.endpoint, units) for target in targets)

    monkeypatch.setattr(
        "pioreactor.web.api.cache.invalidate_multicast_get_cache", fake_invalidate_multicast_get_cache
    )
    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_post", lambda *args, **kwargs: "task")
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post(
        "/api/workers/unit1/calibrations/media_pump",
        json={"calibration_data": _build_valid_calibration_yaml("uploaded_for_cache"), "set_as_active": True},
    )

    assert response.status_code == 202
    assert captured_calls == [
        ("calibrations", "/unit_api/calibrations", ["unit1"]),
        ("active_calibrations", "/unit_api/active_calibrations", ["unit1"]),
    ]


def test_get_all_estimators_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/estimators")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "estimators"
    assert captured["endpoint"] == "/unit_api/estimators"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_get_all_active_estimators_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/workers/$broadcast/active_estimators")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "active_estimators"
    assert captured["endpoint"] == "/unit_api/active_estimators"
    assert captured["units"] == ["unit4", "unit3", "unit2", "unit1"]
    assert captured["timeout"] == 5.0


def test_set_active_estimator_invalidates_estimator_cache(client, monkeypatch: MonkeyPatch) -> None:
    captured_calls: list[tuple[str, str, list[str]]] = []

    def fake_invalidate_multicast_get_cache(targets: list[object], units: list[str]) -> None:
        captured_calls.extend((target.namespace, target.endpoint, units) for target in targets)

    monkeypatch.setattr(
        "pioreactor.web.api.cache.invalidate_multicast_get_cache", fake_invalidate_multicast_get_cache
    )
    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_patch", lambda *args, **kwargs: "task")
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.patch("/api/workers/unit1/active_estimators/od90/example-estimator")

    assert response.status_code == 202
    assert captured_calls == [
        ("active_estimators", "/unit_api/active_estimators", ["unit1"]),
        ("estimators", "/unit_api/estimators", ["unit1"]),
    ]


def test_get_plugins_on_machine_queues_cached_multicast_get(client, monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_cached_multicast_get(target: object, units: list[str], timeout: float = 5.0) -> str:
        captured["cache_namespace"] = target.namespace
        captured["endpoint"] = target.endpoint
        captured["units"] = units
        captured["timeout"] = timeout
        return "task"

    monkeypatch.setattr("pioreactor.web.api.cache.cached_multicast_get", fake_cached_multicast_get)
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.get("/api/units/$broadcast/plugins/installed")

    assert response.status_code == 202
    assert captured["cache_namespace"] == "plugins_installed"
    assert captured["endpoint"] == "/unit_api/plugins/installed"
    assert set(captured["units"]) == {"localhost", "unit1", "unit2", "unit3", "unit4"}
    assert captured["timeout"] == 5.0


def test_install_plugin_invalidates_plugins_cache(client, monkeypatch: MonkeyPatch) -> None:
    captured_calls: list[tuple[str, str, list[str]]] = []

    def fake_invalidate_multicast_get_cache(targets: list[object], units: list[str]) -> None:
        captured_calls.extend((target.namespace, target.endpoint, units) for target in targets)

    monkeypatch.setattr(
        "pioreactor.web.api.cache.invalidate_multicast_get_cache", fake_invalidate_multicast_get_cache
    )
    monkeypatch.setattr("pioreactor.web.api.tasks.multicast_post", lambda *args, **kwargs: "task")
    monkeypatch.setattr("pioreactor.web.api.create_task_response", lambda task: ({"task": task}, 202))

    response = client.post("/api/units/unit1/plugins/install", json={"args": ["example-plugin"]})

    assert response.status_code == 202
    assert captured_calls == [
        ("plugins_installed", "/unit_api/plugins/installed", ["unit1"]),
        ("calibration_protocols", "/unit_api/calibration_protocols", ["unit1"]),
    ]
