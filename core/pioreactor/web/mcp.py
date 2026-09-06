# -*- coding: utf-8 -*-
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from time import sleep
from typing import Any
from typing import cast
from urllib.parse import quote

import msgspec
from flask import Blueprint
from flask import jsonify
from flask import request
from flask import Response
from flask import send_file
from mcp_utils.core import MCPServer
from mcp_utils.schema import MCPErrorResponse
from mcp_utils.schema import ToolAnnotations
from mcp_utils.schema import ToolInfo
from pioreactor.config import get_leader_hostname
from pioreactor.mureq import HTTPException
from pioreactor.paths import get_run_pioreactor_path
from pioreactor.pubsub import delete_from_leader as _delete_from_leader
from pioreactor.pubsub import get_from_leader as _get_from_leader
from pioreactor.pubsub import patch_into_leader as _patch_into_leader
from pioreactor.pubsub import post_into_leader as _post_into_leader
from pioreactor.pubsub import put_into_leader as _put_into_leader
from pioreactor.web.app import query_app_db
from pioreactor.web.plugin_registry import registered_mcp_tools
from pioreactor.web.utils import is_valid_unix_filename


logger = logging.getLogger("mcp_utils")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


MCP_APP_NAME = "pioreactor_mcp"
MCP_VERSION = "0.3.0"
INSTRUCTIONS = """
Use this MCP server to control a Pioreactor cluster of workers. Basic summary:
 - a leader Pioreactor controls multiple worker Pioreactors (the leader can also be a worker)
 - workers should be assigned to an experiment and be "active" before running jobs
 - jobs have settings, some of which can be modified in real-time
 - discover unit capabilities before launching jobs; option names use CLI hyphens,
   while live settings use the published setting names (often underscores)
 - "$broadcast" affects the scope described by each tool; specify a unit for individual control
 - a successful launch acknowledges dispatch, not completion of the job or physical action
 - null unit results mean unavailable, not an empty inventory
 - experiment profiles can be used to run sequences of jobs automatically
"""


mcp = MCPServer(MCP_APP_NAME, MCP_VERSION, instructions=INSTRUCTIONS)


def _get_exports_dir() -> Path:
    return get_run_pioreactor_path() / "exports"


def _build_export_artifact_response(filename: str) -> dict[str, Any]:
    export_path = _get_exports_dir() / filename
    artifact: dict[str, Any] = {
        "artifact_id": filename,
        "filename": filename,
        "mime_type": "application/zip",
        "download_path": f"/mcp/artifacts/exports/{filename}",
        "leader_local_path": export_path.as_posix(),
    }
    if export_path.exists():
        artifact["size_bytes"] = export_path.stat().st_size

    return {
        "result": True,
        "artifact": artifact,
        "msg": "Finished",
    }


def _request_into_leader(
    method: str,
    endpoint: str,
    request_fn: Callable[..., Any],
    *,
    json: dict[str, Any] | None = None,
    unwrap_task_result: bool = False,
) -> Any:
    # Bound polling without resubmitting the original mutation.
    deadline = monotonic() + 30.0
    while True:
        response = request_fn(endpoint, json=json) if json is not None else request_fn(endpoint)
        try:
            response.raise_for_status()
        except HTTPException as exc:
            raise HTTPException(
                f"{method} {endpoint} failed (HTTP {response.status_code}): "
                f"{response.content.decode('utf-8', errors='replace')[:2000]}"
            ) from exc

        content = response.json() if response.content else None
        if response.status_code == 202 and isinstance(content, dict) and "result_url_path" in content:
            endpoint = content["result_url_path"]
            if monotonic() >= deadline:
                raise TimeoutError(
                    f"Task {content.get('task_id', '')} is still pending at {endpoint}. "
                    "The operation may still complete; do not resubmit it. "
                    "Check running jobs or the task result URL before taking further action."
                )
            sleep(0.25)
            method, request_fn, json = "GET", _get_from_leader, None
            unwrap_task_result = True
            continue

        if unwrap_task_result and isinstance(content, dict) and "task_id" in content:
            if content.get("status") == "succeeded":
                return content["result"]
            if content.get("status") == "failed":
                raise HTTPException(content.get("error") or f"Task at {endpoint} failed.")
            raise HTTPException(f"Unexpected task status {content.get('status')} for {endpoint}.")

        if method == "GET" and response.status_code != 200:
            raise HTTPException(f"Unexpected status code {response.status_code} for GET {endpoint}.")

        return content


def get_from_leader(endpoint: str) -> Any:
    """Wrapper around `get_from_leader` to handle errors and callback checks."""
    return _request_into_leader("GET", endpoint, _get_from_leader, unwrap_task_result=True)


def post_into_leader(endpoint: str, json: dict[str, Any] | None = None) -> Any:
    """Wrapper around `post_into_leader` to handle errors."""
    return _request_into_leader("POST", endpoint, _post_into_leader, json=json)


def patch_into_leader(endpoint: str, json: dict[str, Any] | None = None) -> Any:
    """Wrapper around `patch_into_leader` to handle errors."""
    return _request_into_leader("PATCH", endpoint, _patch_into_leader, json=json)


def put_into_leader(endpoint: str, json: dict[str, Any] | None = None) -> Any:
    """Wrapper around `put_into_leader` to handle errors."""
    return _request_into_leader("PUT", endpoint, _put_into_leader, json=json)


def delete_from_leader(endpoint: str, json: dict[str, Any] | None = None) -> Any:
    """Wrapper around `delete_from_leader` to handle errors."""
    return _request_into_leader("DELETE", endpoint, _delete_from_leader, json=json)


def get_experiments(active_only: bool = False) -> list[dict[str, Any]]:
    """
    List experiments (name, creation timestamp, description, hours since creation).

    If active_only, list experiments with at least one active worker assigned.
    """
    if active_only:
        return get_from_leader("/api/experiments/active")
    else:
        return get_from_leader("/api/experiments")


@mcp.tool()
def create_experiment(
    experiment: str,
    description: str | None = None,
) -> dict[str, Any]:
    """
    Create a new experiment record with optional metadata about media and organism.
    """
    payload: dict[str, str] = {"experiment": experiment}
    if description is not None:
        payload["description"] = description
    return post_into_leader("/api/experiments", json=payload)


def get_pioreactor_workers(active_only: bool = False) -> list[dict[str, Any]]:
    """
    Return the worker inventory with experiment assignments. If *active_only*, filter by `is_active`.

    Common requests include "list worker assignments", "list pioreactors", "list cluster inventory"
    or "which pioreactors are running experiments".
    """
    workers = cast(list[dict[str, Any]], get_from_leader("/api/workers/assignments"))
    return [w for w in workers if w.get("is_active")] if active_only else [w for w in workers]


@mcp.tool()
def assign_worker_to_experiment(experiment: str, pioreactor_unit: str) -> dict[str, Any]:
    """
    Assign a specific worker to an experiment so it can participate in experiment activities.
    """
    payload = {"pioreactor_unit": pioreactor_unit}
    return put_into_leader(f"/api/experiments/{quote(experiment, safe="")}/workers", json=payload)


@mcp.tool()
def unassign_worker_from_experiment(experiment: str, pioreactor_unit: str) -> dict[str, Any]:
    """
    Remove a worker from an experiment and stop any jobs scoped to that experiment on the worker.
    """
    return delete_from_leader(
        f"/api/experiments/{quote(experiment, safe="")}/workers/{quote(pioreactor_unit, safe="")}"
    )


def _condense_capabilities(capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Condense capabilities to a summary format with job name, automation name (if any),
    and lists of argument and option names.
    """
    condensed_caps: list[dict[str, Any]] = []

    for cap in capabilities:
        entry: dict[str, Any] = {"job_name": cap["job_name"]}
        if cap.get("automation_name"):
            entry["automation_name"] = cap["automation_name"]
        entry["arguments"] = [arg["name"] for arg in cap.get("arguments", [])]
        entry["options"] = [
            opt["long_flag"] for opt in cap.get("options", [])
        ]  # don't use name, it is not case-sensitive
        condensed_caps.append(entry)
    return condensed_caps


def _summarize_capabilities(capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return a slimmer, invocation-focused capability summary.

    This intentionally drops verbose descriptor internals while keeping enough
    information to understand what can be run and how.
    """
    summarized_caps: list[dict[str, Any]] = []

    for cap in capabilities:
        entry: dict[str, Any] = {"job_name": cap["job_name"]}

        if cap.get("automation_name"):
            entry["automation_name"] = cap["automation_name"]

        if cap.get("help"):
            entry["help"] = cap["help"]

        arguments = []
        for arg in cap.get("arguments", []):
            argument_entry = {"name": arg["name"]}
            if arg.get("required"):
                argument_entry["required"] = arg["required"]
            if arg.get("type"):
                argument_entry["type"] = arg["type"]
            if "nargs" in arg:
                argument_entry["nargs"] = arg["nargs"]
            arguments.append(argument_entry)
        if arguments:
            entry["arguments"] = arguments

        options = []
        for opt in cap.get("options", []):
            option_entry = {"name": opt["long_flag"]}
            if opt.get("required"):
                option_entry["required"] = opt["required"]
            if opt.get("type"):
                option_entry["type"] = opt["type"]
            if opt.get("default") is not None:
                option_entry["default"] = opt["default"]
            for key in ("help", "multiple"):
                if key in opt:
                    option_entry[key] = opt[key]
            options.append(option_entry)
        if options:
            entry["options"] = options

        published_settings = []
        for setting_name, setting_meta in cap.get("published_settings", {}).items():
            setting_entry = {"name": setting_name}
            if setting_meta.get("settable") is not None:
                setting_entry["settable"] = setting_meta["settable"]
            if setting_meta.get("datatype"):
                setting_entry["datatype"] = setting_meta["datatype"]
            if setting_meta.get("unit"):
                setting_entry["unit"] = setting_meta["unit"]
            published_settings.append(setting_entry)
        if published_settings:
            entry["published_settings"] = published_settings

        if cap.get("cli_example"):
            entry["cli_example"] = cap["cli_example"]

        summarized_caps.append(entry)

    return summarized_caps


def get_pioreactor_unit_capabilities(pioreactor_unit: str, condensed: bool = False) -> dict[str, Any]:
    """
    List all `pio run` subcommands and their args/options, and published settings.

    If condensed is True, return a summary of each capability including only
    the job name, automation name (if any), and lists of argument and option names.
    Otherwise, return a slimmer invocation-focused summary instead of the raw verbose descriptors.
    """
    caps = cast(
        dict[str, list[dict[str, Any]] | None],
        get_from_leader(f"/api/units/{quote(pioreactor_unit, safe="")}/capabilities"),
    )
    if condensed:
        return {
            unit_: _condense_capabilities(caps_) if caps_ is not None else None
            for unit_, caps_ in caps.items()
        }
    return {
        unit_: _summarize_capabilities(caps_) if caps_ is not None else None for unit_, caps_ in caps.items()
    }


@mcp.tool()
def run_job_or_action_on_pioreactor_unit(
    pioreactor_unit: str,
    job_or_action: str,
    experiment: str,
    options: dict[str, str | int | float | bool | None] | None = None,
    arguments: list[str] | None = None,
) -> dict[str, Any]:
    """
    Launch an action or job on a *pioreactor_unit/worker* within *experiment*.

    This runs `pio run` with the specified job or action name, options, and arguments on the unit(s).

    Parameters:
        pioreactor_unit: target unit name (or "$broadcast" to address all units assigned to the experiment).
        job_or_action: name of the job to run. See `get_pioreactor_unit_capabilities` for available jobs and options.
        experiment: experiment identifier under which to launch the job.
        options: JSON object using CLI option names without leading dashes, e.g. {"target-rpm": 500}. Use null for flags without values.
        arguments: list of required positional arguments for the job entry-point.
    """
    payload = {
        "options": options or {},
        "args": arguments or [],
        "env": {"JOB_SOURCE": "mcp"},
        "config_overrides": [],
    }
    return post_into_leader(
        f"/api/workers/{quote(pioreactor_unit, safe="")}/jobs/run/job_name/{quote(job_or_action, safe="")}/experiments/{quote(experiment, safe="")}",
        json=payload,
    )


@mcp.tool()
def export_experiment_data(
    experiment: str,
    dataset_names: list[str],
    partition_by_unit: bool = False,
    partition_by_experiment: bool = True,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """
    Export datasets from the leader database and return a retrievable artifact handle.

    start_time and end_time must be ISO-8601 timestamps with Z or a numeric UTC offset.
    Both bounds are inclusive.

    The returned `download_path` can be fetched from this MCP server, and `leader_local_path`
    points to where the file was written on the leader.
    """
    response = post_into_leader(
        "/api/datasets/exportable/export",
        json={
            "datasets": dataset_names,
            "experiment": experiment,
            "partition_by_unit": partition_by_unit,
            "partition_by_experiment": partition_by_experiment,
            "start_time": start_time,
            "end_time": end_time,
        },
    )

    filename = response.get("filename")
    if not isinstance(filename, str) or not filename:
        raise ValueError("Export completed but the API did not return a valid filename.")

    return _build_export_artifact_response(filename)


@mcp.tool()
def update_pioreactor_unit_job_settings(
    pioreactor_unit: str, job: str, experiment: str, settings: dict[str, Any]
) -> dict[str, Any]:
    """
    Update the current settings for a job on a unit/worker within an experiment.
    Use "$broadcast" for all workers assigned to this experiment.
    Only published settings marked settable can be changed.
    """
    return patch_into_leader(
        f"/api/workers/{quote(pioreactor_unit, safe="")}/jobs/update/job_name/{quote(job, safe="")}/experiments/{quote(experiment, safe="")}",
        json={"settings": settings},
    )


@mcp.tool()
def stop_job_on_pioreactor_unit(
    experiment: str, pioreactor_unit: str, job: str | None = None
) -> dict[str, Any]:
    """
    Stop running jobs. If `job` parameter is None, stop all jobs associated the experiment for the unit.
    Specify pioreactor_unit explicitly; "$broadcast" targets all workers in the experiment.

    Users may say "stop all jobs", "stop job <job> in <experiment>", "stop unit <unit> jobs",
    or "stop all jobs in experiment <experiment>".
    """
    if job is None:
        return post_into_leader(
            f"/api/workers/{quote(pioreactor_unit, safe="")}/jobs/stop/experiments/{quote(experiment, safe="")}"
        )
    else:
        return post_into_leader(
            f"/api/workers/{quote(pioreactor_unit, safe="")}/jobs/stop/job_name/{quote(job, safe="")}/experiments/{quote(experiment, safe="")}"
        )


def get_jobs_running_on_pioreactor_unit(pioreactor_unit: str) -> dict[str, Any]:
    """
    Return list of running jobs on *unit/worker*.
    Target all units with "$broadcast".
    """
    return get_from_leader(f"/api/workers/{quote(pioreactor_unit, safe="")}/jobs/running")


def get_recent_experiment_logs(experiment: str, lines: int = 50) -> list[dict[str, Any]]:
    """
    Return the latest experiment logs. lines must be between 1 and 1000.
    """
    if not 1 <= lines <= 1000:
        raise ValueError("lines must be between 1 and 1000.")
    return get_from_leader(f"/api/experiments/{quote(experiment, safe="")}/recent_logs?lines={lines}")


@mcp.tool()
def blink_pioreactor_unit(pioreactor_unit: str) -> dict[str, Any]:
    """
    Blink the onboard blue LED of a specific unit.
    Target all units with "$broadcast".
    """
    return post_into_leader(f"/api/workers/{quote(pioreactor_unit, safe="")}/blink")


@mcp.tool()
def reboot_pioreactor_unit(pioreactor_unit: str) -> dict[str, Any]:
    """
    Reboot/restart a specific unit/worker.
    Target all units with "$broadcast".

    """
    return post_into_leader(f"/api/units/{quote(pioreactor_unit, safe="")}/system/reboot")


@mcp.tool()
def shutdown_pioreactor_unit(pioreactor_unit: str) -> dict[str, Any]:
    """
    Shutdown a specific unit/worker.
    Target all units with "$broadcast".
    """
    return post_into_leader(f"/api/units/{quote(pioreactor_unit, safe="")}/system/shutdown")


def get_current_job_settings_for_pioreactor_unit(
    pioreactor_unit: str, job_name: str, experiment: str
) -> dict[str, Any]:
    """
    List settings for a job on a unit/worker.

    Target all units with "$broadcast".
    """
    return get_from_leader(
        f"/api/workers/{quote(pioreactor_unit, safe="")}/jobs/settings/job_name/{quote(job_name, safe="")}/experiments/{quote(experiment, safe="")}"
    )


def get_experiment_profiles() -> list[dict[str, Any]]:
    """
    Profiles are pre-defined "scripts" that execute commands as certain times (like a recipe.)

    List available experiment profiles (filename, fullpath, and parsed metadata).
    """
    return get_from_leader("/api/experiment_profiles")


@mcp.tool()
def run_experiment_profile(
    profile: str,
    experiment: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Profiles are pre-defined "scripts" that execute commands as certain times (like a recipe.)

    Execute a saved profile on the leader, coordinating workers in the experiment.
    profile is the filename returned by get_experiment_profiles. dry_run simulates execution.
    """
    options = {"dry-run": None} if dry_run else {}
    args = ["execute", profile, experiment]
    return run_job_or_action_on_pioreactor_unit(
        get_leader_hostname(), "experiment_profile", experiment, options=options, arguments=args
    )


def db_get_tables() -> list[dict[str, Any]]:
    """List tables in the application database."""
    tables = query_app_db(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    )
    assert isinstance(tables, list)
    return tables


def db_get_table_schema(table_name: str) -> list[dict[str, Any]]:
    """Get schema for the specified table."""
    exists = query_app_db("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
    if not exists:
        raise ValueError(f"Table '{table_name}' does not exist in the database.")
    schema = query_app_db("SELECT * FROM pragma_table_info(?);", (table_name,))
    assert isinstance(schema, list)
    return schema


def db_query_db(
    query: str,
    parameters: list[str | int | float | bool | None] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Run a single read-only SELECT (including WITH queries) against the application database.

    Discover tables and columns with db_get_tables and db_get_table_schema first.
    Use ? placeholders with parameters for values. Returns rows, row_count, and truncated.
    At most limit rows are returned; use SQL aggregation or explicit pagination for larger datasets.
    """
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000.")
    # A subquery admits SELECTs only, preventing PRAGMA/ATTACH and other connection mutations.
    rows = query_app_db(
        f"SELECT * FROM (\n{query.strip().removesuffix(';')}\n) LIMIT ?",
        (*(parameters or []), limit + 1),
    )
    assert isinstance(rows, list)
    return {"rows": rows[:limit], "row_count": min(len(rows), limit), "truncated": len(rows) > limit}


def get_pioreactor_unit_configuration(pioreactor_unit: str) -> dict[str, Any]:
    """Get merged configuration for a given unit from shared config.ini plus the unit's local unit_config.ini."""
    return get_from_leader(f"/api/config/units/{quote(pioreactor_unit, safe="")}")


# The library's decorator exposes only name; register discovery metadata through its public API.
for read_tool in (
    get_experiments,
    get_pioreactor_workers,
    get_pioreactor_unit_capabilities,
    get_jobs_running_on_pioreactor_unit,
    get_recent_experiment_logs,
    get_current_job_settings_for_pioreactor_unit,
    get_experiment_profiles,
    db_get_tables,
    db_get_table_schema,
    db_query_db,
    get_pioreactor_unit_configuration,
):
    tool_info = ToolInfo.from_callable(read_tool, name=read_tool.__name__)
    tool_info.annotations = ToolAnnotations(readOnlyHint=True)
    # mcp-utils strips Annotated metadata, so publish bounds here and validate in the tools.
    if read_tool in (db_query_db, get_recent_experiment_logs):
        parameter_name = "limit" if read_tool is db_query_db else "lines"
        tool_info.inputSchema["properties"][parameter_name].update(minimum=1, maximum=1000)
    mcp.register_tool(read_tool.__name__, read_tool, tool_info)


for tool, kwargs in registered_mcp_tools():
    mcp.tool(**kwargs)(tool)


mcp_bp = Blueprint("mcp", __name__, url_prefix="/mcp")


# Current invariant: the MCP root accepts both /mcp and /mcp/ without redirecting.
@mcp_bp.post("/", strict_slashes=False)
def handle_mcp() -> Response:
    origin = request.headers.get("Origin")
    if origin is not None and origin.rstrip("/") != request.host_url.rstrip("/"):
        return Response(status=403)

    payload = request.get_json(force=True, silent=False)

    result = mcp.handle_message(payload, http_headers=dict(request.headers))
    if result is None:
        return Response(status=202)

    response = jsonify(msgspec.to_builtins(result))
    if isinstance(result, MCPErrorResponse):
        response.status_code = result.http_status_code
    return response


@mcp_bp.get("/artifacts/exports/<filename>")
def get_export_artifact(filename: str) -> Response:
    safe_filename = Path(filename).name
    if (
        safe_filename != filename
        or not is_valid_unix_filename(safe_filename)
        or not safe_filename.endswith(".zip")
    ):
        return Response("Invalid artifact filename.", status=400)

    export_path = (_get_exports_dir() / safe_filename).resolve()
    if not export_path.exists():
        return Response("Artifact not found.", status=404)

    return send_file(export_path, mimetype="application/zip", as_attachment=True)
