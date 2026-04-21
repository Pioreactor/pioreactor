# -*- coding: utf-8 -*-
"""
Tests for the MCP (Model-Context-Protocol) blueprint and helper functions.
"""
import pytest
from pioreactor.mureq import HTTPException
from pioreactor.web.mcp import assign_workers_to_experiment
from pioreactor.web.mcp import create_experiment
from pioreactor.web.mcp import export_experiment_data
from pioreactor.web.mcp import get_experiments
from pioreactor.web.mcp import get_pioreactor_unit_capabilties
from pioreactor.web.mcp import run_job_or_action_on_pioreactor_unit
from pioreactor.web.mcp import unassign_worker_from_experiment
from pioreactor.web.mcp import wrap_result_as_dict

from .conftest import capture_requests


def test_wrap_result_as_dict_wraps_and_passthrough() -> None:
    """wrap_result_as_dict should wrap non-dict return values and pass through dicts."""

    @wrap_result_as_dict
    def returns_str() -> str:
        return "hello"

    @wrap_result_as_dict
    def returns_dict() -> dict:
        return {"key": "value"}

    assert returns_str() == {"result": "hello"}
    assert returns_dict() == {"key": "value"}


def test_mcp_blueprint_registration(app) -> None:
    """The MCP blueprint should be registered under the 'mcp' key with prefix '/mcp'."""
    assert "mcp" in app.blueprints
    routes = {rule.rule for rule in app.url_map.iter_rules() if rule.endpoint.startswith("mcp.")}
    assert "/mcp/" in routes


def test_get_experiments_invokes_correct_leader_endpoint() -> None:
    """get_experiments(active_only=False) should call the standard /api/experiments endpoint."""
    with capture_requests() as requests:
        result = get_experiments(False)
    assert requests, "Expected at least one HTTP request"
    assert requests[0].path == "/api/experiments"
    assert result == {"mocked": "response"}


def test_get_experiments_active_only_invokes_active_endpoint() -> None:
    """get_experiments(active_only=True) should call /api/experiments/active."""
    with capture_requests() as requests:
        result = get_experiments(True)
    assert requests and requests[0].path == "/api/experiments/active"
    assert result == {"mocked": "response"}


def test_create_experiment_posts_expected_payload() -> None:
    """create_experiment should POST experiment metadata to the leader."""
    with capture_requests() as requests:
        result = create_experiment(
            "new-experiment",
            description="A test experiment",
        )
    assert requests, "Expected HTTP request to be captured"
    req = requests[0]
    assert req.method == "POST"
    assert req.path == "/api/experiments"
    assert req.json == {
        "experiment": "new-experiment",
        "description": "A test experiment",
    }
    assert result == {"mocked": "response"}


def test_assign_workers_to_experiment_puts_assignment_payload() -> None:
    """assign_workers_to_experiment should PUT the worker assignment payload."""
    with capture_requests() as requests:
        result = assign_workers_to_experiment("exp1", "worker1")
    assert requests, "Expected HTTP request to be captured"
    req = requests[0]
    assert req.method == "PUT"
    assert req.path == "/api/experiments/exp1/workers"
    assert req.json == {"pioreactor_unit": "worker1"}
    assert result == {"mocked": "response"}


def test_unassign_worker_from_experiment_deletes_assignment() -> None:
    """unassign_worker_from_experiment should DELETE the assignment resource."""
    with capture_requests() as requests:
        result = unassign_worker_from_experiment("exp1", "worker1")
    assert requests, "Expected HTTP request to be captured"
    req = requests[0]
    assert req.method == "DELETE"
    assert req.path == "/api/experiments/exp1/workers/worker1"
    assert req.json is None
    assert result == {"mocked": "response"}


def test_get_from_leader_raises_on_failed_task_payload(monkeypatch) -> None:
    class DummyResponse:
        status_code = 200
        content = b'{"task_id":"task-1","status":"failed","error":"No such command."}'

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"task_id": "task-1", "status": "failed", "error": "No such command."}

    monkeypatch.setattr("pioreactor.web.mcp._get_from_leader", lambda endpoint: DummyResponse())

    with pytest.raises(HTTPException, match="No such command."):
        get_experiments(False)


def test_run_job_accepts_json_string_options() -> None:
    """run_job_or_action_on_pioreactor_unit should accept JSON object strings for options."""
    with capture_requests() as requests:
        result = run_job_or_action_on_pioreactor_unit(
            "worker1",
            "stirring",
            "exp1",
            options='{"target-rpm": 500, "enable-dodging-od": false}',
        )

    assert requests, "Expected HTTP request to be captured"
    req = requests[0]
    assert req.method == "POST"
    assert req.path == "/api/workers/worker1/jobs/run/job_name/stirring/experiments/exp1"
    assert req.json["options"] == {"target-rpm": 500, "enable-dodging-od": False}
    assert result == {"mocked": "response"}


def test_export_experiment_data_returns_artifact_handle(tmp_path, monkeypatch) -> None:
    """export_experiment_data should return a retrievable artifact payload."""
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    monkeypatch.setenv("RUN_PIOREACTOR", str(tmp_path))
    filename = "export_20260410193000.zip"
    export_path = exports_dir / filename
    export_path.write_bytes(b"zip-bytes")

    with capture_requests() as requests:
        with monkeypatch.context() as m:
            m.setattr(
                "pioreactor.web.mcp.post_into_leader",
                lambda endpoint, json=None: {"result": True, "filename": filename, "msg": "Finished"},
            )
            result = export_experiment_data(
                experiments=["noise data 2"],
                dataset_names=["stirring_rates"],
            )

    assert not requests, "The post_into_leader helper is patched directly in this test."
    assert result["result"] is True
    assert result["artifact"]["artifact_id"] == filename
    assert result["artifact"]["filename"] == filename
    assert result["artifact"]["download_path"] == f"/mcp/artifacts/exports/{filename}"
    assert result["artifact"]["leader_local_path"] == export_path.as_posix()
    assert result["artifact"]["size_bytes"] == len(b"zip-bytes")


def test_mcp_export_artifact_route_serves_zip(app, client, tmp_path, monkeypatch) -> None:
    """The MCP artifact route should serve exported zip files from the leader exports directory."""
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    monkeypatch.setenv("RUN_PIOREACTOR", str(tmp_path))
    filename = "export_20260410193000.zip"
    payload = b"zip-bytes"
    (exports_dir / filename).write_bytes(payload)

    response = client.get(f"/mcp/artifacts/exports/{filename}")

    assert response.status_code == 200
    assert response.data == payload
    assert response.mimetype == "application/zip"


def test_get_pioreactor_unit_capabilities_returns_slim_summary(monkeypatch) -> None:
    """Default capability responses should be slimmer than the raw unit_api descriptors."""
    monkeypatch.setattr(
        "pioreactor.web.mcp.get_from_leader",
        lambda _endpoint: {
            "xr1": [
                {
                    "job_name": "stirring",
                    "help": "Start the stirring of the Pioreactor.",
                    "arguments": [],
                    "options": [
                        {
                            "name": "target_rpm",
                            "long_flag": "target-rpm",
                            "required": False,
                            "default": None,
                            "type": "float range",
                            "help": "set the target RPM",
                        }
                    ],
                    "published_settings": {
                        "target_rpm": {"datatype": "float", "settable": True, "unit": "RPM"},
                        "$state": {"datatype": "text", "settable": True},
                    },
                    "cli_example": "pio run stirring [OPTIONS]",
                }
            ]
        },
    )

    result = get_pioreactor_unit_capabilties("xr1", condensed=False)

    assert result == {
        "xr1": [
            {
                "job_name": "stirring",
                "help": "Start the stirring of the Pioreactor.",
                "options": [{"name": "target-rpm", "type": "float range"}],
                "published_settings": [
                    {"name": "target_rpm", "settable": True, "datatype": "float", "unit": "RPM"},
                    {"name": "$state", "settable": True, "datatype": "text"},
                ],
                "cli_example": "pio run stirring [OPTIONS]",
            }
        ]
    }


def test_get_pioreactor_unit_capabilities_condensed_still_returns_shortest_view(monkeypatch) -> None:
    monkeypatch.setattr(
        "pioreactor.web.mcp.get_from_leader",
        lambda _endpoint: {
            "xr1": [
                {
                    "job_name": "stirring",
                    "automation_name": None,
                    "arguments": [{"name": "filename"}],
                    "options": [{"long_flag": "target-rpm"}],
                }
            ]
        },
    )

    result = get_pioreactor_unit_capabilties("xr1", condensed=True)

    assert result == {"xr1": [{"job_name": "stirring", "arguments": ["filename"], "options": ["target-rpm"]}]}


def test_endpoints_exist_in_api_and_unit_api(app) -> None:
    """Ensure key routes from api.py and unit_api.py are registered on the app."""
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    # sample API routes
    assert "/api/experiments" in routes
    assert "/api/experiments/<experiment>" in routes
    assert "/api/experiments/active" in routes
    # sample unit_api route
    assert "/unit_api/task_results/<task_id>" in routes
    # MCP endpoint
    assert "/mcp/" in routes

    # additional API routes used by MCP blueprint
    assert "/api/workers/assignments" in routes
    assert "/api/units/<pioreactor_unit>/capabilities" in routes
    assert "/api/workers/<pioreactor_unit>/capabilities" in routes
    assert "/api/workers/<pioreactor_unit>/jobs/run/job_name/<job_name>/experiments/<experiment>" in routes
    assert "/api/units/<pioreactor_unit>/jobs/run/job_name/<job_name>/experiments/<experiment>" in routes
    assert "/api/workers/<pioreactor_unit>/jobs/update/job_name/<job_name>/experiments/<experiment>" in routes
    assert "/api/units/<pioreactor_unit>/jobs/update/job_name/<job_name>/experiments/<experiment>" in routes
    assert "/api/workers/<pioreactor_unit>/bioreactor/update/experiments/<experiment>" in routes
    assert "/api/workers/<pioreactor_unit>/jobs/stop/experiments/<experiment>" in routes
    assert "/api/workers/<pioreactor_unit>/jobs/stop/job_name/<job_name>/experiments/<experiment>" in routes
    assert "/api/units/<pioreactor_unit>/jobs/stop/job_name/<job_name>/experiments/<experiment>" in routes
    assert "/api/workers/<pioreactor_unit>/jobs/running" in routes
    assert "/api/units/<pioreactor_unit>/jobs/running" in routes
    assert "/api/workers/<pioreactor_unit>/blink" in routes
    assert "/api/units/<pioreactor_unit>/system/reboot" in routes
    assert "/api/units/<pioreactor_unit>/system/shutdown" in routes
    assert (
        "/api/workers/<pioreactor_unit>/jobs/settings/job_name/<job_name>/experiments/<experiment>" in routes
    )
    assert "/api/experiments/<experiment>/recent_logs" in routes
    assert "/api/experiment_profiles" in routes
    assert "/api/config/units/<pioreactor_unit>" in routes
    assert "/api/automations/descriptors/<automation_type>" in routes
    assert "/api/workers/<pioreactor_unit>/automations/descriptors/<automation_type>" in routes
    assert "/api/jobs/descriptors" in routes
    assert "/api/workers/<pioreactor_unit>/jobs/descriptors" in routes
    assert "/api/charts/descriptors" in routes
    assert "/api/datasets/exportable" in routes
    assert "/mcp/artifacts/exports/<filename>" in routes
