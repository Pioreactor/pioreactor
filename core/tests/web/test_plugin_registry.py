# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from pioreactor.web import plugin_registry


@pytest.fixture(autouse=True)
def reset_plugin_registry(monkeypatch):
    monkeypatch.setattr(plugin_registry, "_api_routes", [])
    monkeypatch.setattr(plugin_registry, "_unit_api_routes", [])
    monkeypatch.setattr(plugin_registry, "_mcp_tools", [])


def test_register_api_route_records_rule_and_returns_original_function() -> None:
    def handler() -> str:
        return "demo"

    decorated = plugin_registry.register_api_route("/demo", methods=["GET"])(handler)

    assert decorated is handler
    routes = plugin_registry.registered_api_routes()
    assert isinstance(routes, tuple)
    assert routes == (("/demo", {"methods": ["GET"]}, handler),)


def test_register_unit_api_route_records_independently() -> None:
    def handler() -> str:
        return "unit"

    plugin_registry.register_unit_api_route("/unit/<identifier>", methods=["POST"])(handler)

    assert plugin_registry.registered_api_routes() == ()
    unit_routes = plugin_registry.registered_unit_api_routes()
    assert isinstance(unit_routes, tuple)
    assert unit_routes == (("/unit/<identifier>", {"methods": ["POST"]}, handler),)


def test_register_mcp_tool_copies_tool_kwargs() -> None:
    tool_kwargs = {"timeout": 5, "description": "tool"}

    def tool() -> str:
        return "ok"

    plugin_registry.register_mcp_tool(tool_kwargs=tool_kwargs)(tool)
    tool_kwargs["timeout"] = 10

    registered = plugin_registry.registered_mcp_tools()
    assert isinstance(registered, tuple)
    assert registered == ((tool, {"timeout": 5, "description": "tool"}),)
    assert registered[0][1] is not tool_kwargs
