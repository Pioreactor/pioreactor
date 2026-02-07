#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import ast
import json
import re
import warnings
from http import HTTPStatus
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = (
    REPO_ROOT / "core" / "pioreactor" / "web" / "api.py",
    REPO_ROOT / "core" / "pioreactor" / "web" / "unit_api.py",
)
DEFAULT_OUTPUT_DIR = REPO_ROOT
DEFAULT_OUTPUT_FILENAMES = {
    "api.py": "API_ENDPOINTS.md",
    "unit_api.py": "UNIT_API_ENDPOINTS.md",
}

MUTATING_METHODS = {"POST", "PATCH", "PUT"}
PATH_PARAM_TYPE_MAP = {
    "string": "string",
    "path": "string",
    "int": "integer",
    "float": "number",
    "uuid": "string",
}
PATH_PARAM_DESCRIPTIONS = {
    "pioreactor_unit": "Unit name or `$broadcast` where supported.",
    "experiment": "Experiment identifier.",
    "job_name": "Job name.",
    "task_id": "Background task identifier.",
    "device": "Target device name.",
    "calibration_name": "Calibration name.",
    "estimator_name": "Estimator name.",
    "filename": "Filename.",
    "target": "Requested target.",
    "setting": "Setting name.",
    "data_source": "Time-series data source.",
    "column": "Column name.",
    "automation_type": "Automation type.",
    "target_dataset": "Dataset identifier.",
    "session_id": "Calibration session identifier.",
    "req_path": "Requested path segment.",
}
ACRONYMS = {"api", "id", "od", "utc", "ip", "ui", "db"}
STRUCT_TYPE_REQUEST_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "ArgsOptionsEnvs": {
        "options": {"option_name": "value"},
        "env": {"ENV_VAR": "value"},
        "args": ["--some-flag"],
    },
    "ArgsOptionsEnvsConfigOverrides": {
        "options": {"target_rpm": "200"},
        "env": {"JOB_SOURCE": "user"},
        "args": ["--some-flag"],
        "config_overrides": [["stirring.config", "pwm_hz", "100"]],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate markdown documentation for Flask API endpoints.")
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Source file to inspect (can be provided multiple times). Defaults to api.py and unit_api.py.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Output markdown path for single-source generation. "
            "If omitted, writes one file per source into core/pioreactor/web."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=(
            "Directory for per-source output files when --output is not provided. "
            f"Default: {DEFAULT_OUTPUT_DIR.relative_to(REPO_ROOT)}"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_paths = [
        Path(source).resolve() for source in (args.sources or [str(path) for path in DEFAULT_SOURCES])
    ]
    output_paths: list[Path] = []

    if args.output:
        if len(source_paths) != 1:
            raise ValueError("When --output is provided, pass exactly one --source.")
        source_path = source_paths[0]
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        endpoints = extract_endpoints_from_source(source_path)
        endpoints.sort(key=lambda endpoint: (endpoint["path"], endpoint["method"], endpoint["title"]))

        output_path = Path(args.output).resolve()
        markdown = render_markdown(endpoints, [source_path])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        output_paths.append(output_path)
        print(f"Wrote {len(endpoints)} endpoint docs to {output_path}")
        return 0

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for source_path in source_paths:
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        endpoints = extract_endpoints_from_source(source_path)
        endpoints.sort(key=lambda endpoint: (endpoint["path"], endpoint["method"], endpoint["title"]))

        output_filename = infer_output_filename(source_path)
        output_path = output_dir / output_filename
        markdown = render_markdown(endpoints, [source_path])
        output_path.write_text(markdown, encoding="utf-8")
        output_paths.append(output_path)
        print(f"Wrote {len(endpoints)} endpoint docs to {output_path}")

    return 0


def extract_endpoints_from_source(source_path: Path) -> list[dict[str, Any]]:
    source = source_path.read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        module = ast.parse(source, filename=str(source_path))
    blueprint_prefixes = find_blueprint_prefixes(module)
    endpoints: list[dict[str, Any]] = []

    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        routes = extract_routes_for_function(node, blueprint_prefixes)
        if not routes:
            continue

        title = function_name_to_title(node.name)
        docstring = ast.get_docstring(node) or ""
        description = first_nonempty_line(docstring) or f"{title} endpoint."
        success_status, success_payload = infer_success_response(node)
        request_body_from_docstring = parse_json_block_from_docstring(docstring)
        request_body_from_type = infer_typed_request_body_example(node)
        request_body_keys = infer_json_request_keys(node)
        reads_body = function_reads_request_body(node)

        for route in routes:
            request_body_example = None
            if route["method"] in MUTATING_METHODS:
                if request_body_from_docstring is not None:
                    request_body_example = request_body_from_docstring
                elif request_body_from_type is not None:
                    request_body_example = request_body_from_type
                elif request_body_keys:
                    request_body_example = {key: "<value>" for key in request_body_keys}
                elif reads_body:
                    request_body_example = {"<request_body>": "<see implementation>"}

            endpoints.append(
                {
                    "title": title,
                    "description": description,
                    "method": route["method"],
                    "path": route["path"],
                    "path_params": parse_path_parameters(route["path"], route["defaults"]),
                    "request_body_example": request_body_example,
                    "success_status": success_status,
                    "success_payload": success_payload,
                    "source": source_path,
                }
            )

    return endpoints


def find_blueprint_prefixes(module: ast.Module) -> dict[str, str]:
    prefixes: dict[str, str] = {}

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if not is_name(node.value.func, "Blueprint"):
            continue

        url_prefix = get_call_keyword_string(node.value, "url_prefix")
        if url_prefix is None:
            continue

        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = url_prefix

    return prefixes


def extract_routes_for_function(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    blueprint_prefixes: dict[str, str],
) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []

    for decorator in function_node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute):
            continue
        if decorator.func.attr != "route":
            continue
        if not isinstance(decorator.func.value, ast.Name):
            continue

        blueprint_name = decorator.func.value.id
        if blueprint_name not in blueprint_prefixes:
            continue

        route_path = get_first_call_arg_string(decorator)
        if route_path is None:
            continue

        full_path = f"{blueprint_prefixes[blueprint_name]}{route_path}"
        methods = extract_methods_from_route_decorator(decorator)
        defaults = extract_defaults_from_route_decorator(decorator)

        for method in methods:
            routes.append({"method": method, "path": full_path, "defaults": defaults})

    return routes


def extract_methods_from_route_decorator(route_decorator: ast.Call) -> list[str]:
    methods_node = get_call_keyword_node(route_decorator, "methods")
    if methods_node is None:
        return ["GET"]

    method_values = extract_string_values_from_collection(methods_node)
    if not method_values:
        return ["GET"]

    return sorted({method.upper() for method in method_values})


def extract_defaults_from_route_decorator(route_decorator: ast.Call) -> set[str]:
    defaults_node = get_call_keyword_node(route_decorator, "defaults")
    if defaults_node is None or not isinstance(defaults_node, ast.Dict):
        return set()

    defaults: set[str] = set()
    for key_node in defaults_node.keys:
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            defaults.add(key_node.value)
    return defaults


def infer_success_response(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, Any | None]:
    discovered: list[tuple[int, int, Any | None]] = []
    return_nodes = [node for node in iter_function_nodes(function_node) if isinstance(node, ast.Return)]
    return_nodes.sort(key=lambda node: node.lineno)

    for return_node in return_nodes:
        if return_node.value is None:
            continue
        parsed = parse_return_expression(return_node.value)
        if parsed is None:
            continue
        status, payload = parsed
        discovered.append((return_node.lineno, status, payload))

    discovered.sort(key=score_return_candidate)
    for _, status, payload in discovered:
        if 200 <= status < 300:
            return status, payload

    if discovered:
        _, status, payload = discovered[0]
        return status, payload

    return 200, None


def parse_return_expression(expression: ast.AST) -> tuple[int, Any | None] | None:
    if isinstance(expression, ast.Tuple) and len(expression.elts) >= 2:
        maybe_status = parse_int_constant(expression.elts[1])
        if maybe_status is not None:
            payload = parse_response_payload(expression.elts[0])
            return maybe_status, payload

    if is_call_to_named_function(expression, "create_task_response"):
        return 202, {
            "unit": "<unit>",
            "task_id": "<task_id>",
            "result_url_path": "/unit_api/task_results/<task_id>",
        }

    payload = parse_response_payload(expression)
    if payload is not None:
        return 200, payload

    return None


def parse_response_payload(expression: ast.AST) -> Any | None:
    parsed = ast_node_to_builtin(expression)
    if parsed is not None:
        return parsed

    if isinstance(expression, ast.Call):
        if is_call_to_named_function(expression, "attach_cache_control") and expression.args:
            return parse_response_payload(expression.args[0])

        if is_call_to_named_function(expression, "jsonify") and expression.args:
            return ast_node_to_builtin(expression.args[0])

        if is_call_to_named_function(expression, "as_json_response") and expression.args:
            json_blob = parse_string_constant(expression.args[0])
            if json_blob is None:
                return None
            try:
                return json.loads(json_blob)
            except json.JSONDecodeError:
                return None

    return None


def parse_path_parameters(path: str, optional_parameters: set[str]) -> list[dict[str, str]]:
    parameters: list[dict[str, str]] = []
    for token in re.findall(r"<([^>]+)>", path):
        converter = "string"
        name = token
        if ":" in token:
            converter, name = token.split(":", 1)

        parameter_type = PATH_PARAM_TYPE_MAP.get(converter, "string")
        description = PATH_PARAM_DESCRIPTIONS.get(name, "Path parameter.")
        if converter == "path" and name not in PATH_PARAM_DESCRIPTIONS:
            description = "Path segment, may include '/'."

        parameters.append(
            {
                "name": name,
                "type": parameter_type,
                "required": "No" if name in optional_parameters else "Yes",
                "description": description,
            }
        )
    return parameters


def infer_json_request_keys(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    json_variable_names: set[str] = set()

    for node in iter_function_nodes(function_node):
        if isinstance(node, ast.Assign) and is_json_body_load_expression(node.value):
            for target in node.targets:
                json_variable_names.update(extract_assigned_names(target))
        elif isinstance(node, ast.AnnAssign) and node.value and is_json_body_load_expression(node.value):
            json_variable_names.update(extract_assigned_names(node.target))

    if not json_variable_names:
        return []

    keys: set[str] = set()
    for node in iter_function_nodes(function_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and isinstance(node.func.value, ast.Name):
                if node.func.value.id in json_variable_names and node.args:
                    key = parse_string_constant(node.args[0])
                    if key is not None:
                        keys.add(key)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id in json_variable_names:
                key = parse_subscript_key(node.slice)
                if key is not None:
                    keys.add(key)

    return sorted(keys)


def function_reads_request_body(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if any(is_json_body_load_expression(node) for node in iter_function_nodes(function_node)):
        return True

    for node in iter_function_nodes(function_node):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "request" and node.attr in {"data", "files", "form"}:
                return True

    return False


def infer_typed_request_body_example(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, Any] | None:
    for node in iter_function_nodes(function_node):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get_json":
            continue

        type_kw = get_call_keyword_node(node, "type")
        if type_kw is None:
            continue
        type_name = extract_type_name(type_kw)
        if type_name is None:
            continue
        if type_name in STRUCT_TYPE_REQUEST_BODY_EXAMPLES:
            return STRUCT_TYPE_REQUEST_BODY_EXAMPLES[type_name]
    return None


def is_json_body_load_expression(expression: ast.AST) -> bool:
    if isinstance(expression, ast.Call):
        if isinstance(expression.func, ast.Attribute):
            if isinstance(expression.func.value, ast.Name):
                owner = expression.func.value.id
                if expression.func.attr == "get_json" and owner in {"request", "current_app"}:
                    return True
        return False

    if isinstance(expression, ast.BoolOp):
        return any(is_json_body_load_expression(value) for value in expression.values)

    return False


def parse_json_block_from_docstring(docstring: str) -> Any | None:
    if not docstring:
        return None

    matches = re.findall(r"```json\s*([\s\S]*?)\s*```", docstring, flags=re.IGNORECASE)
    if not matches:
        return None

    block = matches[0].strip()
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        return None


def render_markdown(endpoints: list[dict[str, Any]], source_paths: list[Path]) -> str:
    lines: list[str] = []
    for endpoint in endpoints:
        lines.append(f"## {endpoint['title']}")
        lines.append("")
        lines.append(endpoint["description"])
        lines.append("")
        lines.append("### Endpoint")
        lines.append(f"`{endpoint['method']} {flask_path_to_docs_path(endpoint['path'])}`")
        lines.append("")

        has_request_section = bool(endpoint["path_params"] or endpoint["request_body_example"] is not None)
        if has_request_section:
            lines.append("### Request")
            lines.append("")

            if endpoint["path_params"]:
                lines.append("#### Path Parameters")
                lines.append("| Name | Type | Required | Description |")
                lines.append("| ---- | ---- | -------- | ----------- |")
                for path_param in endpoint["path_params"]:
                    lines.append(
                        f"| {path_param['name']} | {path_param['type']} | {path_param['required']} | {path_param['description']} |"
                    )
                lines.append("")

            if endpoint["request_body_example"] is not None:
                lines.append("#### Request Body")
                lines.append("```json")
                lines.append(json.dumps(endpoint["request_body_example"], indent=2, ensure_ascii=True))
                lines.append("```")
                lines.append("")

        lines.append("### Response")
        lines.append("")
        lines.append("#### Success")
        lines.append("")
        status = endpoint["success_status"]
        lines.append(f"**Status:** `{format_status(status)}`")
        lines.append("")
        if endpoint["success_payload"] is not None:
            lines.append("```json")
            lines.append(json.dumps(endpoint["success_payload"], indent=2, ensure_ascii=True))
            lines.append("```")
        else:
            lines.append("_No response body example inferred._")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_status(code: int) -> str:
    try:
        phrase = HTTPStatus(code).phrase
    except ValueError:
        phrase = ""
    return f"{code} {phrase}".strip()


def parse_subscript_key(slice_node: ast.AST) -> str | None:
    if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
        return slice_node.value
    return None


def ast_node_to_builtin(node: ast.AST) -> Any | None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (str, int, float, bool)) or node.value is None:
            return node.value
        return str(node.value)

    if isinstance(node, ast.Name):
        return f"<{node.id}>"

    if isinstance(node, ast.Attribute):
        parent = ast_node_to_builtin(node.value)
        if isinstance(parent, str):
            parent = parent.strip("<>")
        return f"<{parent}.{node.attr}>"

    if isinstance(node, ast.JoinedStr):
        return "<string>"

    if isinstance(node, ast.List):
        list_values: list[Any] = []
        for element in node.elts:
            parsed = ast_node_to_builtin(element)
            list_values.append("<value>" if parsed is None else parsed)
        return list_values

    if isinstance(node, ast.Tuple):
        tuple_values: list[Any] = []
        for element in node.elts:
            parsed = ast_node_to_builtin(element)
            tuple_values.append("<value>" if parsed is None else parsed)
        return tuple_values

    if isinstance(node, ast.Set):
        set_values: list[Any] = []
        for element in node.elts:
            parsed = ast_node_to_builtin(element)
            set_values.append("<value>" if parsed is None else parsed)
        return set_values

    if isinstance(node, ast.Dict):
        result: dict[str, Any] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                continue
            key = ast_node_to_builtin(key_node)
            if not isinstance(key, str):
                continue
            value = ast_node_to_builtin(value_node)
            result[key] = "<value>" if value is None else value
        return result

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = ast_node_to_builtin(node.operand)
        if isinstance(value, (int, float)):
            return -value
        return None

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = ast_node_to_builtin(node.left)
        right = ast_node_to_builtin(node.right)
        if isinstance(left, dict) and isinstance(right, dict):
            return left | right
        return None

    return None


def get_call_keyword_node(call_node: ast.Call, keyword_name: str) -> ast.AST | None:
    for keyword in call_node.keywords:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


def get_call_keyword_string(call_node: ast.Call, keyword_name: str) -> str | None:
    keyword_node = get_call_keyword_node(call_node, keyword_name)
    if keyword_node is None:
        return None
    return parse_string_constant(keyword_node)


def get_first_call_arg_string(call_node: ast.Call) -> str | None:
    if not call_node.args:
        return None
    return parse_string_constant(call_node.args[0])


def extract_string_values_from_collection(node: ast.AST) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: list[str] = []
        for element in node.elts:
            value = parse_string_constant(element)
            if value is not None:
                values.append(value)
        return values

    string_value = parse_string_constant(node)
    if string_value is not None:
        return [string_value]
    return []


def parse_string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def parse_int_constant(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def is_name(node: ast.AST, value: str) -> bool:
    return isinstance(node, ast.Name) and node.id == value


def is_call_to_named_function(node: ast.AST, function_name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id == function_name
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == function_name
    return False


def extract_assigned_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in target.elts:
            names.update(extract_assigned_names(item))
        return names
    return set()


def first_nonempty_line(docstring: str) -> str:
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def function_name_to_title(function_name: str) -> str:
    words = [word for word in function_name.strip("_").split("_") if word]
    formatted: list[str] = []
    for word in words:
        if word in ACRONYMS:
            formatted.append(word.upper())
        else:
            formatted.append(word.capitalize())
    return " ".join(formatted) if formatted else "Endpoint"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def infer_output_filename(source_path: Path) -> str:
    if source_path.name in DEFAULT_OUTPUT_FILENAMES:
        return DEFAULT_OUTPUT_FILENAMES[source_path.name]

    stem = source_path.stem.upper()
    sanitized = re.sub(r"[^A-Z0-9_]+", "_", stem).strip("_")
    if not sanitized:
        sanitized = "ENDPOINTS"
    return f"{sanitized}_ENDPOINTS.md"


def extract_type_name(type_node: ast.AST) -> str | None:
    if isinstance(type_node, ast.Name):
        return type_node.id
    if isinstance(type_node, ast.Attribute):
        return type_node.attr
    return None


def iter_function_nodes(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> Any:
    for child in ast.iter_child_nodes(function_node):
        yield from iter_nodes_without_nested_scopes(child)


def iter_nodes_without_nested_scopes(node: ast.AST) -> Any:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from iter_nodes_without_nested_scopes(child)


def score_return_candidate(candidate: tuple[int, int, Any | None]) -> tuple[int, int, int]:
    _, status, payload = candidate
    status_score = 0 if 200 <= status < 300 else 1

    if isinstance(payload, dict):
        payload_score = 0
    elif isinstance(payload, list):
        payload_score = 1
    elif payload is None:
        payload_score = 3
    else:
        payload_score = 2

    return (status_score, payload_score, status)


def flask_path_to_docs_path(path: str) -> str:
    return re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", r"{\1}", path)


if __name__ == "__main__":
    raise SystemExit(main())
