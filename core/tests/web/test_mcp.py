# -*- coding: utf-8 -*-
"""
Tests for the MCP (Model-Context-Protocol) blueprint and helper functions.
"""
from pioreactor.web.mcp import assign_workers_to_experiment
from pioreactor.web.mcp import create_experiment
from pioreactor.web.mcp import get_experiments
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
    assert "/api/contrib/experiment_profiles" in routes
    assert "/api/units/<pioreactor_unit>/configuration" in routes
