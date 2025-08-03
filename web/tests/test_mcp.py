# -*- coding: utf-8 -*-
"""
Tests for the MCP (Model-Context-Protocol) blueprint and helper functions.
"""
from __future__ import annotations

from pioreactorui.mcp import get_experiments
from pioreactorui.mcp import wrap_result_as_dict

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


def test_handle_mcp_invalid_payload(client) -> None:
    """POSTing an empty payload to /mcp should return a 400 Bad Request."""
    resp = client.post("/mcp/", json={})
    # JSON-RPC error for missing id should return HTTP 200 with an error object
    assert resp.status_code == 200
    data = resp.get_json()
    assert "error" in data
    # Missing message id is the expected error
    assert data["error"]["message"] == "Missing message id"


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
