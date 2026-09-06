# -*- coding: utf-8 -*-
"""
Tests for the MCP (Model-Context-Protocol) blueprint and helper functions.
"""
import sqlite3
from unittest.mock import Mock

import msgspec
import pytest
from pioreactor.mureq import HTTPException
from pioreactor.mureq import Response
from pioreactor.web.mcp import assign_worker_to_experiment
from pioreactor.web.mcp import create_experiment
from pioreactor.web.mcp import db_query_db
from pioreactor.web.mcp import export_experiment_data
from pioreactor.web.mcp import get_experiments
from pioreactor.web.mcp import get_pioreactor_unit_capabilities
from pioreactor.web.mcp import get_recent_experiment_logs
from pioreactor.web.mcp import mcp
from pioreactor.web.mcp import post_into_leader
from pioreactor.web.mcp import run_job_or_action_on_pioreactor_unit
from pioreactor.web.mcp import unassign_worker_from_experiment

from .conftest import capture_requests


def test_mcp_blueprint_registration(app) -> None:
    """The MCP blueprint should be registered under the 'mcp' key with prefix '/mcp'."""
    assert "mcp" in app.blueprints
    routes = {rule.rule for rule in app.url_map.iter_rules() if rule.endpoint.startswith("mcp.")}
    assert "/mcp/" in routes


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_mcp_endpoint_accepts_optional_trailing_slash(client, monkeypatch, path: str) -> None:
    monkeypatch.setattr("pioreactor.web.mcp.mcp.handle_message", lambda payload, **kwargs: None)

    response = client.post(path, json={})

    assert response.status_code == 202
    assert "Location" not in response.headers


def test_mcp_endpoint_supports_modern_discovery(client) -> None:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "discover-1",
            "method": "server/discover",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        },
        headers={
            "Origin": "http://localhost",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "server/discover",
        },
    )

    assert response.status_code == 200
    assert response.json["result"]["supportedVersions"] == ["2026-07-28"]
    assert response.json["result"]["resultType"] == "complete"
    assert response.json["result"]["capabilities"]["tools"] == {"listChanged": False}
    assert "Mcp-Session-Id" not in response.headers


def test_mcp_endpoint_rejects_missing_client_capabilities(client) -> None:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "tools-1",
            "method": "tools/list",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                }
            },
        },
        headers={
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "tools/list",
        },
    )

    assert response.status_code == 400
    assert response.json["error"]["code"] == -32602


def test_mcp_endpoint_returns_not_found_for_unknown_method(client) -> None:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "unknown-1",
            "method": "unknown/method",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        },
        headers={
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "unknown/method",
        },
    )

    assert response.status_code == 404
    assert response.json["error"]["code"] == -32601


def test_mcp_endpoint_rejects_cross_origin_requests(client) -> None:
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "discover-1",
            "method": "server/discover",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        },
        headers={
            "Origin": "https://example.invalid",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "server/discover",
        },
    )

    assert response.status_code == 403


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


def test_assign_worker_to_experiment_puts_assignment_payload() -> None:
    """assign_worker_to_experiment should PUT the worker assignment payload."""
    with capture_requests() as requests:
        result = assign_worker_to_experiment("exp1", "worker1")
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


def test_run_job_accepts_object_options() -> None:
    """run_job_or_action_on_pioreactor_unit should accept JSON objects for options."""
    with capture_requests() as requests:
        result = run_job_or_action_on_pioreactor_unit(
            "worker1",
            "stirring",
            "exp1",
            options={"target-rpm": 500, "enable-dodging-od": False},
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
                experiment="noise data 2",
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
                        "$state": {"datatype": "string", "settable": True},
                    },
                    "cli_example": "pio run stirring [OPTIONS]",
                }
            ]
        },
    )

    result = get_pioreactor_unit_capabilities("xr1", condensed=False)

    assert result == {
        "xr1": [
            {
                "job_name": "stirring",
                "help": "Start the stirring of the Pioreactor.",
                "options": [{"name": "target-rpm", "type": "float range", "help": "set the target RPM"}],
                "published_settings": [
                    {"name": "target_rpm", "settable": True, "datatype": "float", "unit": "RPM"},
                    {"name": "$state", "settable": True, "datatype": "string"},
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

    result = get_pioreactor_unit_capabilities("xr1", condensed=True)

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


def test_task_polling_handles_scalar_results_without_resubmission(monkeypatch) -> None:

    submit = Mock(return_value=Response("", 202, {}, b'{"result_url_path":"/unit_api/task_results/1"}'))
    poll = Mock(
        side_effect=[
            Response("", 202, {}, b'{"result_url_path":"/unit_api/task_results/1","status":"pending"}'),
            Response("", 200, {}, b'{"task_id":"1","status":"succeeded","result":true}'),
        ]
    )
    monkeypatch.setattr("pioreactor.web.mcp._post_into_leader", submit)
    monkeypatch.setattr("pioreactor.web.mcp._get_from_leader", poll)
    monkeypatch.setattr("pioreactor.web.mcp.sleep", lambda _: None)

    assert post_into_leader("/api/example", json={"x": 1}) is True
    submit.assert_called_once_with("/api/example", json={"x": 1})
    assert poll.call_count == 2


def test_task_polling_times_out_without_resubmission(monkeypatch) -> None:

    submit = Mock(
        return_value=Response("", 202, {}, b'{"task_id":"1","result_url_path":"/unit_api/task_results/1"}')
    )
    monkeypatch.setattr("pioreactor.web.mcp._post_into_leader", submit)
    monkeypatch.setattr("pioreactor.web.mcp.monotonic", Mock(side_effect=[0, 31]))

    with pytest.raises(TimeoutError, match="do not resubmit"):
        post_into_leader("/api/example")
    submit.assert_called_once()


def test_capabilities_distinguish_unavailable_from_empty(monkeypatch) -> None:
    monkeypatch.setattr("pioreactor.web.mcp.get_from_leader", lambda _: {"offline": None, "empty": []})
    assert get_pioreactor_unit_capabilities("$broadcast") == {"offline": None, "empty": []}
    assert get_pioreactor_unit_capabilities("$broadcast", condensed=True) == {"offline": None, "empty": []}


def test_experiment_identifiers_are_url_encoded(monkeypatch) -> None:

    get = Mock(return_value=[])
    monkeypatch.setattr("pioreactor.web.mcp._get_from_leader", get)

    get.return_value = Response("", 200, {}, b"[]")
    assert get_recent_experiment_logs("culture #1?x=y") == []
    get.assert_called_once_with("/api/experiments/culture%20%231%3Fx%3Dy/recent_logs?lines=50")


def test_db_query_bounds_rows_and_accepts_parameters(app) -> None:

    assert db_query_db("SELECT ? AS value UNION ALL SELECT ?;", ["a", "b"], limit=1) == {
        "rows": [{"value": "a"}],
        "row_count": 1,
        "truncated": True,
    }
    assert db_query_db("SELECT ? AS value", ["a"], limit=1) == {
        "rows": [{"value": "a"}],
        "row_count": 1,
        "truncated": False,
    }


@pytest.mark.parametrize(
    "query", ["PRAGMA query_only=0", "ATTACH DATABASE ':memory:' AS extra", "DELETE FROM experiments"]
)
def test_db_query_rejects_non_select_statements(app, query: str) -> None:

    with pytest.raises(sqlite3.OperationalError):
        db_query_db(query)


def test_mcp_tool_discovery_contract() -> None:

    response = mcp.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        }
    )
    tools = {tool["name"]: tool for tool in msgspec.to_builtins(response)["result"]["tools"]}
    assert "get_pioreactor_unit_capabilities" in tools
    assert "get_pioreactor_unit_capabilties" not in tools
    assert "pioreactor_unit" in tools["stop_job_on_pioreactor_unit"]["inputSchema"]["required"]
    assert tools["db_query_db"]["inputSchema"]["properties"]["limit"]["maximum"] == 1000


@pytest.mark.parametrize(
    "arguments",
    [
        {"pioreactor_unit": "worker1", "job_or_action": "stirring", "experiment": "exp", "options": "{}"},
        {
            "pioreactor_unit": "worker1",
            "job_or_action": "stirring",
            "experiment": "exp",
            "options": {"x": []},
        },
    ],
)
def test_mcp_rejects_invalid_options_before_dispatch(monkeypatch, arguments: dict) -> None:

    submit = Mock()
    monkeypatch.setattr("pioreactor.web.mcp._post_into_leader", submit)
    response = mcp.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "run_job_or_action_on_pioreactor_unit",
                "arguments": arguments,
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
            },
        }
    )
    assert msgspec.to_builtins(response)["result"]["isError"] is True
    submit.assert_not_called()


@pytest.mark.parametrize(
    "status,body,is_error",
    [
        (200, b'[{"experiment":"culture"}]', False),
        (400, b'{"error":"Unknown experiment culture"}', True),
    ],
)
def test_mcp_returns_structured_arrays_and_actionable_http_errors(
    monkeypatch, status: int, body: bytes, is_error: bool
) -> None:
    monkeypatch.setattr("pioreactor.web.mcp._get_from_leader", lambda _: Response("", status, {}, body))
    response = mcp.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_experiments",
                "arguments": {},
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
            },
        }
    )
    result = msgspec.to_builtins(response)["result"]
    assert result.get("isError", False) is is_error
    if is_error:
        assert "Unknown experiment culture" in result["content"][0]["text"]
        assert "HTTP 400" in result["content"][0]["text"]
    else:
        assert result["structuredContent"] == [{"experiment": "culture"}]


@pytest.mark.parametrize("value", [0, 1001])
def test_query_and_log_limits_are_enforced_before_io(monkeypatch, value: int) -> None:
    query = Mock()
    get = Mock()
    monkeypatch.setattr("pioreactor.web.mcp.query_app_db", query)
    monkeypatch.setattr("pioreactor.web.mcp.get_from_leader", get)
    with pytest.raises(ValueError, match="between 1 and 1000"):
        db_query_db("SELECT 1", limit=value)
    with pytest.raises(ValueError, match="between 1 and 1000"):
        get_recent_experiment_logs("exp", lines=value)
    query.assert_not_called()
    get.assert_not_called()
