# -*- coding: utf-8 -*-
from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterable
from typing import Tuple

RouteEntry = Tuple[str, Dict[str, Any], Callable[..., Any]]

_api_routes: list[RouteEntry] = []
_unit_api_routes: list[RouteEntry] = []
_mcp_tools: list[tuple[Callable[..., Any], Dict[str, Any]]] = []


def register_api_route(rule: str, **options: Any):
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _api_routes.append((rule, dict(options), func))
        return func

    return decorator


def register_unit_api_route(rule: str, **options: Any):
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _unit_api_routes.append((rule, dict(options), func))
        return func

    return decorator


def register_mcp_tool(*, tool_kwargs: Dict[str, Any] | None = None):
    tool_kwargs = dict(tool_kwargs or {})

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _mcp_tools.append((func, tool_kwargs))
        return func

    return decorator


def registered_api_routes() -> Iterable[RouteEntry]:
    return tuple(_api_routes)


def registered_unit_api_routes() -> Iterable[RouteEntry]:
    return tuple(_unit_api_routes)


def registered_mcp_tools() -> Iterable[tuple[Callable[..., Any], Dict[str, Any]]]:
    return tuple(_mcp_tools)
