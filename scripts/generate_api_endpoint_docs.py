#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate readable markdown endpoint docs for Pioreactor Flask APIs."""
import argparse
import ast
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from typing import NamedTuple


REPO_ROOT = Path(__file__).parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "scratch" / "generated_api_docs"
DEFAULT_BASE_URL = "http://127.0.0.1:4999"
HTTP_STATUS_TEXT = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
}
PATH_PARAM_DESCRIPTIONS = {
    "automation_type": "Automation type, for example `dosing`, `temperature`, or `led`.",
    "calibration_name": "Calibration name.",
    "column": "Dataset column name.",
    "data_source": "Time-series data source name.",
    "device": "Target device name.",
    "estimator_name": "Estimator name.",
    "experiment": "Experiment identifier.",
    "filename": "Filename.",
    "job_name": "Job name.",
    "pioreactor_unit": "Unit name or `$broadcast` where supported.",
    "req_path": "Path under the unit filesystem endpoint.",
    "session_id": "Calibration session identifier.",
    "setting": "Job setting name.",
    "target": "Update target.",
    "target_dataset": "Exportable dataset name.",
    "task_id": "Task identifier.",
}
PATH_PARAM_EXAMPLES = {
    "automation_type": "temperature",
    "calibration_name": "example_calibration",
    "column": "od_filtered",
    "data_source": "od_readings_filtered",
    "device": "od",
    "estimator_name": "example_estimator",
    "experiment": "testing_experiment",
    "filename": "example.yaml",
    "job_name": "stirring",
    "pioreactor_unit": "pio01",
    "req_path": "config.ini",
    "session_id": "session-id",
    "setting": "target_rpm",
    "target": "app",
    "target_dataset": "od_readings",
    "task_id": "task-id",
}
QUERY_PARAM_DESCRIPTIONS = {
    "lookback": "Lookback window in hours. Defaults to `4.0`.",
    "n_rows": "Maximum number of preview rows. Defaults to `5`.",
    "target_points": "Approximate maximum points per series. Defaults to `720` and must be greater than `0`.",
}
QUERY_PARAM_TYPES = {
    "lookback": "number",
    "n_rows": "integer",
    "target_points": "integer",
}
JSON_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "ArgsOptionsEnvsConfigOverrides": {
        "options": {"target_rpm": "200"},
        "env": {"JOB_SOURCE": "api"},
        "args": ["some-flag"],
        "config_overrides": [["stirring.config", "pwm_hz", "100"]],
    },
    "CodePatch": {"code": "[section]\nkey=value\n"},
}
KNOWN_BODY_KEY_EXAMPLES = {
    "args": ["some-flag"],
    "body": "Profile YAML or text content.",
    "calibration_data": {"calibration_name": "example_calibration"},
    "code": "[section]\nkey=value\n",
    "config_overrides": [["stirring.config", "pwm_hz", "100"]],
    "datasets": ["od_readings"],
    "description": "Experiment notes.",
    "end_time": "2026-01-01T12:00:00Z",
    "env": {"JOB_SOURCE": "api"},
    "experiment": "testing_experiment",
    "experiments": ["testing_experiment"],
    "filename": "profile.yaml",
    "is_active": True,
    "label": "Control",
    "level": "INFO",
    "mediaUsed": "LB",
    "message": "Log message.",
    "model_name": "pioreactor_40ml",
    "model_version": "1.5",
    "name": "testing_experiment",
    "new_name": "pio02",
    "options": {"target_rpm": "200"},
    "partition_by_experiment": True,
    "partition_by_unit": True,
    "pioreactor_unit": "pio02",
    "release_archive_location": "/tmp/release.zip",
    "set_as_active": True,
    "source": "api",
    "source_": "api",
    "start_time": "2026-01-01T00:00:00Z",
    "settings": {"target_rpm": "200"},
    "tags": ["screening"],
    "task": "stirring",
    "timestamp": "2026-01-01T00:00:00Z",
    "units": ["pio01"],
    "utc_clock_time": "2026-01-01T00:00:00Z",
    "values": {"current_volume_ml": 12.5},
}


class RouteInfo(NamedTuple):
    method: str
    route: str
    function_name: str
    lineno: int
    docstring: str
    required_body_keys: tuple[str, ...]
    optional_body_keys: tuple[str, ...]
    required_query_keys: tuple[str, ...]
    optional_query_keys: tuple[str, ...]
    body_type_names: tuple[str, ...]
    response_examples: tuple[dict[str, Any], ...]


class LiveSampler:
    def __init__(self, base_url: str, timeout_seconds: float = 1.5) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.workers: list[str] = []
        self.experiments: list[str] = []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate markdown docs for core/pioreactor/web/api.py and unit_api.py."
    )
    parser.add_argument("--api-source", type=Path, default=REPO_ROOT / "core/pioreactor/web/api.py")
    parser.add_argument("--unit-api-source", type=Path, default=REPO_ROOT / "core/pioreactor/web/unit_api.py")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--api-output", type=Path)
    parser.add_argument("--unit-api-output", type=Path)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--live-timeout-seconds",
        type=float,
        default=5.0,
        help="Timeout for each safe live GET sample request.",
    )
    parser.add_argument("--no-live", action="store_true", help="Skip local dev server sampling.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_output = args.api_output or args.output_dir / "api.md"
    unit_api_output = args.unit_api_output or args.output_dir / "unit_api.md"

    sampler = None if args.no_live else build_live_sampler(args.base_url, args.live_timeout_seconds)

    write_endpoint_docs(
        source_path=args.unit_api_source,
        blueprint_name="unit_api_bp",
        url_prefix="/unit_api",
        title="Pioreactor Unit API",
        output_path=unit_api_output,
        sampler=sampler,
    )
    write_endpoint_docs(
        source_path=args.api_source,
        blueprint_name="api_bp",
        url_prefix="/api",
        title="Pioreactor Leader API",
        output_path=api_output,
        sampler=sampler,
    )
    print(
        f"Wrote {api_output.relative_to(REPO_ROOT) if api_output.is_relative_to(REPO_ROOT) else api_output}"
    )
    print(
        "Wrote "
        f"{unit_api_output.relative_to(REPO_ROOT) if unit_api_output.is_relative_to(REPO_ROOT) else unit_api_output}"
    )
    return 0


def write_endpoint_docs(
    *,
    source_path: Path,
    blueprint_name: str,
    url_prefix: str,
    title: str,
    output_path: Path,
    sampler: LiveSampler | None,
) -> None:
    routes = parse_routes(source_path, blueprint_name, url_prefix)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_markdown(title, source_path, routes, sampler, url_prefix),
        encoding="utf-8",
    )


def parse_routes(source_path: Path, blueprint_name: str, url_prefix: str) -> list[RouteInfo]:
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    routes: list[RouteInfo] = []
    for node in module.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        decorator_routes = extract_route_decorators(node.decorator_list, blueprint_name)
        if not decorator_routes:
            continue

        body_summary = inspect_request_body(node)
        query_summary = inspect_query_parameters(node)
        response_examples = infer_response_examples(node)
        docstring = ast.get_docstring(node) or ""
        for route, methods in decorator_routes:
            for method in methods:
                routes.append(
                    RouteInfo(
                        method=method,
                        route=url_prefix + route,
                        function_name=node.name,
                        lineno=node.lineno,
                        docstring=docstring,
                        required_body_keys=tuple(sorted(body_summary["required"])),
                        optional_body_keys=tuple(sorted(body_summary["optional"])),
                        required_query_keys=tuple(sorted(query_summary["required"])),
                        optional_query_keys=tuple(sorted(query_summary["optional"])),
                        body_type_names=tuple(sorted(body_summary["body_type_names"])),
                        response_examples=tuple(response_examples),
                    )
                )
    return sorted(routes, key=lambda route: (route.route, route.method, route.lineno))


def extract_route_decorators(decorators: list[ast.expr], blueprint_name: str) -> list[tuple[str, list[str]]]:
    routes: list[tuple[str, list[str]]] = []
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute):
            continue
        if decorator.func.attr != "route":
            continue
        if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != blueprint_name:
            continue
        if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
            continue

        route = str(decorator.args[0].value)
        methods = ["GET"]
        for keyword in decorator.keywords:
            if keyword.arg == "methods":
                methods = [method.upper() for method in literal_string_list(keyword.value)]
        routes.append((route, methods))
    return routes


def literal_string_list(node: ast.AST) -> list[str]:
    if isinstance(node, ast.List | ast.Tuple):
        return [str(item.value) for item in node.elts if isinstance(item, ast.Constant)]
    return []


def inspect_request_body(node: ast.FunctionDef) -> dict[str, set[str]]:
    aliases = {"request"}
    json_aliases: set[str] = set()
    required: set[str] = set()
    optional: set[str] = set()
    body_type_names: set[str] = set()
    variable_to_json_key: dict[str, str] = {}

    for child in ast.walk(node):
        if isinstance(child, ast.Assign) and is_request_json_expr(child.value):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
                    json_aliases.add(target.id)
        elif (
            isinstance(child, ast.Assign)
            and isinstance(child.value, ast.Call)
            and is_current_app_json_loads_request_data(child.value)
        ):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
                    json_aliases.add(target.id)
            body_type_name = extract_msgspec_type_name(child.value)
            if body_type_name:
                body_type_names.add(body_type_name)
        elif isinstance(child, ast.Assign):
            for target_name, assigned_key in extract_assigned_json_get_keys(child, aliases):
                variable_to_json_key[target_name] = assigned_key
                optional.add(assigned_key)
        elif isinstance(child, ast.Call) and is_current_app_json_loads_request_data(child):
            body_type_name = extract_msgspec_type_name(child)
            if body_type_name:
                body_type_names.add(body_type_name)

    for child in ast.walk(node):
        if isinstance(child, ast.Subscript):
            subscript_key = extract_string_key(child.slice)
            if subscript_key and is_json_alias(child.value, aliases):
                required.add(subscript_key)
        elif (
            isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "get"
        ):
            get_key = extract_string_key(child.args[0]) if child.args else None
            if get_key and is_json_alias(child.func.value, aliases):
                optional.add(get_key)

    optional -= required
    required.update(
        key
        for variable, key in variable_to_json_key.items()
        if variable in variables_checked_as_missing(node)
    )
    for body_type_name in body_type_names:
        required.update(required_keys_for_body_type(body_type_name))
        optional.update(optional_keys_for_body_type(body_type_name))
    optional -= required
    return {"required": required, "optional": optional, "body_type_names": body_type_names}


def extract_assigned_json_get_keys(node: ast.Assign, aliases: set[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for target in node.targets:
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
            key = extract_dict_get_key(node.value, aliases)
            if key is not None:
                pairs.append((target.id, key))
        elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
            for target_elt, value_elt in zip(target.elts, node.value.elts, strict=False):
                if isinstance(target_elt, ast.Name) and isinstance(value_elt, ast.Call):
                    key = extract_dict_get_key(value_elt, aliases)
                    if key is not None:
                        pairs.append((target_elt.id, key))
    return pairs


def inspect_query_parameters(node: ast.FunctionDef) -> dict[str, set[str]]:
    aliases = {"request.args"}
    required: set[str] = set()
    optional: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Assign) and is_request_args_expr(child.value):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
            continue

        if isinstance(child, ast.Subscript):
            key = extract_string_key(child.slice)
            if key and is_query_alias(child.value, aliases):
                required.add(key)
        elif isinstance(child, ast.Call):
            key = extract_dict_get_key(child, aliases)
            if key:
                optional.add(key)
    optional -= required
    return {"required": required, "optional": optional}


def extract_dict_get_key(node: ast.Call, aliases: set[str]) -> str | None:
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        return None
    if is_json_alias(node.func.value, aliases) or is_query_alias(node.func.value, aliases):
        return node.args[0].value
    return None


def variables_checked_as_missing(node: ast.FunctionDef) -> set[str]:
    variables: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.If):
            collect_missing_check_variables(child.test, variables)
    return variables


def collect_missing_check_variables(node: ast.AST, variables: set[str]) -> None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Name):
        variables.add(node.operand.id)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            collect_missing_check_variables(value, variables)


def is_request_json_expr(node: ast.AST) -> bool:
    if isinstance(node, ast.BoolOp):
        return any(is_request_json_expr(value) for value in node.values)
    if isinstance(node, ast.Call):
        return is_request_get_json_call(node)
    if isinstance(node, ast.Attribute):
        return is_request_json_attribute(node)
    return False


def is_request_get_json_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_json"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "request"
    )


def is_request_json_attribute(node: ast.Attribute) -> bool:
    return isinstance(node.value, ast.Name) and node.value.id == "request" and node.attr == "json"


def is_request_args_expr(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "request"
        and node.attr == "args"
    )


def is_query_alias(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.Attribute):
        return dotted_name(node) in aliases or is_request_args_expr(node)
    return False


def is_current_app_json_loads_request_data(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "loads":
        return False
    if not isinstance(node.func.value, ast.Attribute) or node.func.value.attr != "json":
        return False
    if not isinstance(node.func.value.value, ast.Name) or node.func.value.value.id != "current_app":
        return False
    return bool(node.args) and is_request_data_attribute(node.args[0])


def is_request_data_attribute(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "request"


def extract_msgspec_type_name(node: ast.Call) -> str | None:
    for keyword in node.keywords:
        if keyword.arg == "type":
            return dotted_name(keyword.value)
    return None


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def extract_string_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def is_json_alias(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.Attribute) and dotted_name(node) in aliases:
        return True
    if isinstance(node, ast.Call) and is_request_get_json_call(node):
        return True
    if isinstance(node, ast.Attribute) and is_request_json_attribute(node):
        return True
    return False


def required_keys_for_body_type(body_type_name: str) -> set[str]:
    if body_type_name.endswith("CodePatch"):
        return {"code"}
    return set()


def optional_keys_for_body_type(body_type_name: str) -> set[str]:
    if body_type_name.endswith("ArgsOptionsEnvsConfigOverrides"):
        return {"options", "env", "args", "config_overrides"}
    if body_type_name.endswith("ArgsOptionsEnvs"):
        return {"options", "env", "args"}
    return set()


def infer_response_examples(node: ast.FunctionDef) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Return):
            examples.extend(examples_from_return(child.value))
    return unique_examples(examples)


def examples_from_return(node: ast.AST | None) -> list[dict[str, Any]]:
    if node is None:
        return []
    if isinstance(node, ast.Tuple):
        status = extract_status_code(node.elts[1:]) or 200
        body = extract_response_body(node.elts[0])
        return [{"status": status, "body": body}] if body is not None else [{"status": status}]
    body = extract_response_body(node)
    if body is not None:
        return [{"status": 200, "body": body}]
    if isinstance(node, ast.Call) and function_name(node.func) == "create_task_response":
        return [
            {
                "status": 202,
                "body": {
                    "task_id": "abcd1234",
                    "result_url_path": "/unit_api/task_results/abcd1234",
                },
            }
        ]
    return []


def extract_status_code(nodes: Iterable[ast.AST]) -> int | None:
    for node in nodes:
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
    return None


def extract_response_body(node: ast.AST) -> Any | None:
    if isinstance(node, ast.Dict | ast.List | ast.Tuple | ast.Constant):
        return literal_or_placeholder(node)
    if isinstance(node, ast.Call) and function_name(node.func) in {"jsonify", "as_json_response"}:
        if not node.args:
            return None
        return literal_or_placeholder(node.args[0])
    if isinstance(node, ast.Call) and function_name(node.func) == "attach_cache_control":
        if not node.args:
            return None
        return extract_response_body(node.args[0])
    return None


def function_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def literal_or_placeholder(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return placeholder_from_ast(node)


def placeholder_from_ast(node: ast.AST) -> Any:
    if isinstance(node, ast.Dict):
        result: dict[str, Any] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=False):
            key = literal_or_placeholder(key_node) if key_node is not None else "key"
            result[str(key)] = placeholder_from_ast(value_node)
        return result
    if isinstance(node, ast.List | ast.Tuple):
        return [placeholder_from_ast(elt) for elt in node.elts]
    if isinstance(node, ast.Name):
        return f"<{node.id}>"
    if isinstance(node, ast.Call):
        return f"<{function_name(node.func) or 'value'}>"
    if isinstance(node, ast.Attribute):
        return f"<{node.attr}>"
    return "<value>"


def unique_examples(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for example in examples:
        key = json.dumps(example, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        unique.append(example)
    return unique[:3]


def render_markdown(
    title: str,
    source_path: Path,
    routes: list[RouteInfo],
    sampler: LiveSampler | None,
    url_prefix: str,
) -> str:
    lines = frontmatter_and_conventions(url_prefix)
    lines.extend(
        [
            f"# {title}",
            "",
            f"Generated from `{source_path.relative_to(REPO_ROOT)}`.",
            "",
            "> This file is generated. Edit the API source or generator instead of editing this file by hand.",
            "",
            f"Endpoint count: `{len(routes)}`",
            "",
            "## Endpoint Index",
            "",
            "| Method | Path | Handler |",
            "| ------ | ---- | ------- |",
        ]
    )
    for route in routes:
        lines.append(
            f"| `{route.method}` | `{flask_route_to_docs_route(route.route)}` | `{route.function_name}` |"
        )
    lines.append("")

    for route in routes:
        lines.extend(render_route(route, sampler))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def frontmatter_and_conventions(url_prefix: str) -> list[str]:
    if url_prefix == "/api":
        return [
            "---",
            "title: API Reference (Leader /api)",
            "slug: /api-reference",
            "toc_max_heading_level: 2",
            "sidebar_class_name: sidebar-item--updated",
            "---",
            "",
            "### Conventions",
            "",
            "- Only the leader Pioreactor has the `/api` endpoints exposed.",
            "- Async endpoints return `202 Accepted` with a `task_id` and `result_url_path`.",
            "- Poll `GET /unit_api/task_results/{task_id}` until `status` is `succeeded` or `failed`.",
            "- `$broadcast` may be used in path parameters where documented to target all units/workers.",
            "- File download endpoints return binary bodies; use the response content-type to handle them.",
            "- Path parameters are shown inline in the endpoint URL.",
            "- Request/response examples are the canonical shapes; omit optional fields you do not need.",
            "- Errors have the following schema:",
            "",
            "```json",
            "{",
            '  "error": "Human-readable error message",',
            '  "cause": "Human-readable cause (defaults to error if not set)",',
            '  "remediation": "Suggested fix or next step",',
            '  "status": 400',
            "}",
            "```",
            "",
            "Use `/api/workers/...` for worker-only targets (experiment-scoped jobs/logs) and `/api/units/...` when the leader is also a valid target; both accept `$broadcast` where supported.",
            "",
        ]

    if url_prefix == "/unit_api":
        return [
            "---",
            "title: API Reference (Unit /unit_api)",
            "slug: /unit-api-reference",
            "toc_max_heading_level: 2",
            "sidebar_class_name: sidebar-item--updated",
            "---",
            "",
            "### Conventions",
            "",
            "- All Pioreactors have the `/unit_api` endpoints exposed.",
            "- Async endpoints return `202 Accepted` with a `task_id` and `result_url_path`.",
            "- Poll `GET /unit_api/task_results/{task_id}` until `status` is `succeeded` or `failed`.",
            "- File download endpoints return binary bodies; use the response content-type to handle them.",
            "- Path parameters are shown inline in the endpoint URL.",
            "- Request/response examples are the canonical shapes; omit optional fields you do not need.",
            "- Errors have the following schema:",
            "",
            "```json",
            "{",
            '  "error": "Human-readable error message",',
            '  "cause": "Human-readable cause (defaults to error if not set)",',
            '  "remediation": "Suggested fix or next step",',
            '  "status": 400',
            "}",
            "```",
            "",
        ]

    return []


def render_route(route: RouteInfo, sampler: LiveSampler | None) -> list[str]:
    title = humanize_function_name(route.function_name)
    lines = [
        f"## {title}",
        "",
        route_description(route, title),
        "",
        "### Endpoint",
        f"`{route.method} {flask_route_to_docs_route(route.route)}`",
    ]

    request_lines = render_request(route)
    if request_lines:
        lines.extend(["", "### Request", "", *request_lines])

    lines.extend(["", "### Response", "", "#### Success", ""])
    response_example = live_response_example(route, sampler) if sampler else None
    if response_example is None:
        response_example = best_static_response_example(route)

    status = int(response_example.get("status", likely_success_status(route.method)))
    status_text = HTTP_STATUS_TEXT.get(status, "")
    lines.append(f"Status: `{status} {status_text}`" if status_text else f"Status: `{status}`")
    if is_time_series_route(route):
        lines.extend(
            [
                "",
                "Body shape: `series` is a list of series labels. `data` is a parallel list of point arrays, so `data[i]` contains the points for `series[i]`. Each point has `x` as an ISO-8601 UTC timestamp string and `y` as a number.",
            ]
        )
    if "body" in response_example:
        lines.extend(["", "Example body:", "", "```json", json_dumps(response_example["body"]), "```"])
    else:
        note = response_body_note(route)
        lines.extend(["", note if note else "_No example body inferred._"])
    return lines


def route_description(route: RouteInfo, title: str) -> str:
    if not route.docstring:
        return f"{title} endpoint."
    paragraphs = route.docstring.strip().split("\n\n")
    for index, paragraph in enumerate(paragraphs):
        description = normalize_docstring_paragraph(paragraph)
        next_paragraph = paragraphs[index + 1] if index + 1 < len(paragraphs) else ""
        if description and is_docstring_prose_paragraph(paragraph, next_paragraph):
            return description
    return f"{title} endpoint."


def normalize_docstring_paragraph(paragraph: str) -> str:
    return re.sub(r"\s+", " ", paragraph).strip()


def is_docstring_prose_paragraph(paragraph: str, next_paragraph: str = "") -> bool:
    lines = [line.strip() for line in paragraph.strip().splitlines() if line.strip()]
    if not lines:
        return False

    text = " ".join(lines)
    if not re.search(r"[A-Za-z]", text):
        return False

    # Raw Markdown/MDX braces, JSON-ish snippets, shell examples, and placeholder
    # tokens are examples, not prose descriptions.
    code_markers = ("```", "{", "}", "[", "]", "$ ", "curl ", "http://", "https://")
    if any(line.startswith(code_markers) for line in lines):
        return False
    if any(marker in text for marker in ("{", "}", "<", ">")):
        return False
    if is_docstring_code_paragraph(next_paragraph) and not text.endswith((".", "?", "!")):
        return False

    return True


def is_docstring_code_paragraph(paragraph: str) -> bool:
    lines = [line.strip() for line in paragraph.strip().splitlines() if line.strip()]
    if not lines:
        return False
    text = " ".join(lines)
    code_markers = ("```", "{", "}", "[", "]", "$ ", "curl ", "http://", "https://")
    return any(line.startswith(code_markers) for line in lines) or any(
        marker in text for marker in ("{", "}", "<", ">")
    )


def render_request(route: RouteInfo) -> list[str]:
    lines: list[str] = []
    params = path_parameters(route.route)
    if params:
        lines.extend(
            [
                "#### Path Parameters",
                "| Name | Type | Required | Description |",
                "| ---- | ---- | -------- | ----------- |",
            ]
        )
        for param in params:
            description = PATH_PARAM_DESCRIPTIONS.get(param, f"{humanize_identifier(param)}.")
            lines.append(f"| {param} | string | Yes | {description} |")

    if route.required_query_keys or route.optional_query_keys:
        if lines:
            lines.append("")
        lines.extend(
            [
                "#### Query Parameters",
                "| Name | Type | Required | Description |",
                "| ---- | ---- | -------- | ----------- |",
            ]
        )
        for key in route.required_query_keys:
            description = QUERY_PARAM_DESCRIPTIONS.get(key, f"{humanize_identifier(key)}.")
            param_type = QUERY_PARAM_TYPES.get(key, "string")
            lines.append(f"| {key} | {param_type} | Yes | {description} |")
        for key in route.optional_query_keys:
            description = QUERY_PARAM_DESCRIPTIONS.get(key, f"{humanize_identifier(key)}.")
            param_type = QUERY_PARAM_TYPES.get(key, "string")
            lines.append(f"| {key} | {param_type} | No | {description} |")

    body_example = request_body_example(route)
    if body_example is not None:
        if lines:
            lines.append("")
        lines.extend(["#### Request Body"])
        if route.required_body_keys or route.optional_body_keys:
            lines.extend(
                ["", "| Name | Type | Required | Description |", "| ---- | ---- | -------- | ----------- |"]
            )
            for key in route.required_body_keys:
                lines.append(
                    f"| {key} | {json_type_name(body_example.get(key))} | Yes | {humanize_identifier(key)}. |"
                )
            for key in route.optional_body_keys:
                lines.append(
                    f"| {key} | {json_type_name(body_example.get(key))} | No | {humanize_identifier(key)}. |"
                )
            lines.append("")
        lines.extend(["```json", json_dumps(body_example), "```"])
    return lines


def request_body_example(route: RouteInfo) -> dict[str, Any] | None:
    if route.method == "GET":
        return None

    for body_type_name in route.body_type_names:
        short_name = body_type_name.rsplit(".", maxsplit=1)[-1]
        if short_name in JSON_BODY_EXAMPLES:
            return JSON_BODY_EXAMPLES[short_name]

    keys = list(route.required_body_keys) + list(route.optional_body_keys)
    if not keys:
        docstring_example = json_example_from_docstring(route.docstring)
        return docstring_example if isinstance(docstring_example, dict) else None
    return {key: KNOWN_BODY_KEY_EXAMPLES.get(key, example_value_for_unknown_key(key)) for key in keys}


def example_value_for_unknown_key(key: str) -> Any:
    if key.endswith("_at") or key.endswith("_time"):
        return "2026-01-01T00:00:00Z"
    if key.startswith("is_") or key.startswith("has_") or key.startswith("should_"):
        return True
    if key.endswith("_count"):
        return 1
    if key.endswith("_ml"):
        return 1.0
    return f"example_{key}"


def json_example_from_docstring(docstring: str) -> Any | None:
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", docstring, flags=re.DOTALL)
    candidates = [fenced_match.group(1)] if fenced_match else []
    brace_match = re.search(r"(\{(?:.|\n)*\})", docstring)
    if brace_match:
        candidates.append(brace_match.group(1))

    for candidate in candidates:
        cleaned = re.sub(r",(\s*[}\]])", r"\1", candidate)
        cleaned = re.sub(r"<([^>]+)>", r'"\1"', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            continue
    return None


def best_static_response_example(route: RouteInfo) -> dict[str, Any]:
    if is_time_series_route(route):
        return {"status": 200, "body": time_series_response_shape_example()}
    if route.function_name == "get_installed_plugins":
        return {
            "status": 200,
            "body": [
                {
                    "name": "my-example-plugin",
                    "version": "0.2.0",
                    "description": "Plugin description.",
                    "homepage": "https://docs.pioreactor.com",
                    "source": "plugins/example_plugin.py",
                    "author": "Pioreactor",
                }
            ],
        }
    if route.function_name == "get_job_settings":
        return {"status": 200, "body": {"settings": {"target_rpm": "200"}}}
    if route.function_name == "get_job_setting":
        return {"status": 200, "body": {"target_rpm": "200"}}
    if route.function_name in {"list_system_path"}:
        return {
            "status": 200,
            "body": {
                "current": "/home/pioreactor/.pioreactor",
                "dirs": ["experiment_profiles", "plugins", "storage"],
                "files": ["config.ini", "unit_config.ini"],
            },
        }
    if "logs" in route.function_name:
        return {
            "status": 200,
            "body": [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "level": "INFO",
                    "message": "Log message.",
                    "task": "stirring",
                    "source": "app",
                    "pioreactor_unit": "pio01",
                    "experiment": "testing_experiment",
                }
            ],
        }
    if route.function_name in {"create_experiment", "update_experiment", "get_experiment"}:
        return {
            "status": 201 if route.function_name == "create_experiment" else 200,
            "body": {
                "experiment": "testing_experiment",
                "created_at": "2026-01-01T00:00:00Z",
                "description": "Experiment notes.",
                "delta_hours": 0,
                "worker_count": 1,
                "tags": ["screening"],
            },
        }
    if route.function_name in {"get_calibrations_by_device"}:
        return {"status": 200, "body": [{"calibration_name": "example_calibration", "is_active": True}]}
    if route.function_name in {"get_calibration"}:
        return {"status": 200, "body": {"calibration_name": "example_calibration", "is_active": True}}
    if route.function_name in {"get_estimator"}:
        return {"status": 200, "body": {"estimator_name": "example_estimator", "is_active": True}}
    if route.function_name == "upload_system_file":
        return {
            "status": 201,
            "body": {"message": "File successfully uploaded", "save_path": "/tmp/file.zip"},
        }
    if route.function_name == "setup_worker_pioreactor":
        return {"status": 200, "body": {"msg": "Worker pio02 added successfully."}}
    if route.function_name == "preview_exportable_dataset":
        return {
            "status": 200,
            "body": [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "pioreactor_unit": "pio01",
                    "experiment": "testing_experiment",
                }
            ],
        }

    response_examples = [
        example
        for example in route.response_examples
        if "body" not in example or is_helpful_static_example_body(example["body"])
    ]
    if response_examples:
        preferred_status = likely_success_status(route.method)
        for example in response_examples:
            if example.get("status") == preferred_status:
                return dict(example)
        return dict(response_examples[0])
    return {"status": likely_success_status(route.method)}


def response_body_note(route: RouteInfo) -> str | None:
    if route.function_name in {
        "get_shared_config",
        "get_specific_config_for_pioreactor_unit",
        "get_specific_config",
        "get_experiment_profile",
    }:
        return "_Response body is plain text._"
    if route.function_name == "get_installed_plugin":
        return "_Response body is the plugin Python source as plain text._"
    if "zipped" in route.function_name or route.function_name == "import_dot_pioreactor_archive":
        return "_Response body is binary file data._"
    if route.function_name in {
        "reboot_unit",
        "shutdown_unit",
        "start_calibration_session",
        "get_calibration_session",
        "abort_calibration_session",
        "advance_calibration_session",
        "create_calibration",
        "delete_calibration",
        "delete_estimator",
        "update_job",
    }:
        return "_No success response body._"
    return None


def is_time_series_route(route: RouteInfo) -> bool:
    return route.method == "GET" and "/time_series/" in route.route


def time_series_response_shape_example() -> dict[str, Any]:
    return {
        "series": ["pio01", "pio02"],
        "data": [
            [
                {"x": "2026-01-01T00:00:00.000Z", "y": 0.01234},
                {"x": "2026-01-01T00:01:00.000Z", "y": 0.0125},
            ],
            [
                {"x": "2026-01-01T00:00:00.000Z", "y": 0.00987},
                {"x": "2026-01-01T00:01:00.000Z", "y": 0.01001},
            ],
        ],
    }


def is_helpful_static_example_body(value: Any) -> bool:
    return not contains_unhelpful_placeholder(value)


def contains_unhelpful_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(re.fullmatch(r"<[^>]+>", value)) and value != "<truncated>"
    if isinstance(value, list):
        return any(contains_unhelpful_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(contains_unhelpful_placeholder(item) for item in value.values())
    return False


def likely_success_status(method: str) -> int:
    if method == "POST":
        return 201
    if method in {"PATCH", "PUT"}:
        return 200
    return 200


def build_live_sampler(base_url: str, timeout_seconds: float) -> LiveSampler | None:
    sampler = LiveSampler(base_url=base_url.rstrip("/"), timeout_seconds=timeout_seconds)
    if fetch_json(sampler, "/api/health") is None and fetch_json(sampler, "/unit_api/health") is None:
        return None

    workers = fetch_json(sampler, "/api/workers")
    if isinstance(workers, list):
        sampler.workers = [
            row["pioreactor_unit"]
            for row in workers
            if isinstance(row, dict) and isinstance(row.get("pioreactor_unit"), str)
        ]

    latest_experiment = fetch_json(sampler, "/api/experiments/latest")
    if isinstance(latest_experiment, dict) and isinstance(latest_experiment.get("experiment"), str):
        sampler.experiments = [latest_experiment["experiment"]]
    else:
        experiments = fetch_json(sampler, "/api/experiments")
        if isinstance(experiments, list):
            sampler.experiments = [
                row["experiment"]
                for row in experiments
                if isinstance(row, dict) and isinstance(row.get("experiment"), str)
            ]
    return sampler


def live_response_example(route: RouteInfo, sampler: LiveSampler | None) -> dict[str, Any] | None:
    if sampler is None or route.method != "GET" or should_skip_live_get(route.route):
        return None
    path = route_with_examples(route.route, sampler)
    try:
        request = urllib.request.Request(sampler.base_url + path, method="GET")
        with urllib.request.urlopen(request, timeout=sampler.timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                return {"status": response.status}
            body = json.loads(response.read().decode("utf-8"))
            return {"status": response.status, "body": shrink_json(body)}
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def fetch_json(sampler: LiveSampler, path: str) -> Any | None:
    try:
        request = urllib.request.Request(sampler.base_url + path, method="GET")
        with urllib.request.urlopen(request, timeout=sampler.timeout_seconds) as response:
            if "application/json" not in response.headers.get("Content-Type", ""):
                return None
            return json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def should_skip_live_get(route: str) -> bool:
    skipped_fragments = (
        "zipped_",
        "/system/path",
        "/system_logs",
        "/logs",
        "/recent_logs",
        "/time_series/",
        "/preview",
    )
    return any(fragment in route for fragment in skipped_fragments)


def route_with_examples(route: str, sampler: LiveSampler) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1).split(":", maxsplit=1)[-1]
        value = path_param_example(name, sampler)
        return urllib.parse.quote(value, safe="")

    return re.sub(r"<([^>]+)>", replace, route)


def path_param_example(name: str, sampler: LiveSampler) -> str:
    if name == "pioreactor_unit" and sampler.workers:
        return sampler.workers[0]
    if name == "experiment" and sampler.experiments:
        return sampler.experiments[0]
    return PATH_PARAM_EXAMPLES.get(name, f"example_{name}")


def shrink_json(value: Any, depth: int = 0) -> Any:
    if depth >= 6:
        return "<truncated>"
    if isinstance(value, list):
        return [shrink_json(item, depth + 1) for item in value[:3]]
    if isinstance(value, dict):
        items = list(value.items())[:20]
        return {key: shrink_json(item, depth + 1) for key, item in items}
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...<truncated>"
    return value


def path_parameters(route: str) -> list[str]:
    params: list[str] = []
    for match in re.finditer(r"<([^>]+)>", route):
        param = match.group(1).split(":", maxsplit=1)[-1]
        params.append(param)
    return params


def flask_route_to_docs_route(route: str) -> str:
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", route)


def humanize_function_name(name: str) -> str:
    return humanize_identifier(name).title()


def humanize_identifier(name: str) -> str:
    return name.replace("_", " ")


def json_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "string"


def json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=False)


if __name__ == "__main__":
    sys.exit(main())
