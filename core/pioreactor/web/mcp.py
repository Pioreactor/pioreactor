# -*- coding: utf-8 -*-
import json
import logging
import os
import sys
from functools import wraps
from pathlib import Path
from time import sleep
from typing import Any
from typing import Callable
from typing import cast
from typing import Dict
from typing import List

import msgspec
from flask import Blueprint
from flask import jsonify
from flask import request
from flask import Response
from flask import send_file
from mcp_utils.core import MCPServer
from mcp_utils.queue import SQLiteResponseQueue
from pioreactor.config import get_leader_hostname
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import delete_from_leader as _delete_from_leader
from pioreactor.pubsub import get_from_leader as _get_from_leader
from pioreactor.pubsub import patch_into_leader as _patch_into_leader
from pioreactor.pubsub import post_into_leader as _post_into_leader
from pioreactor.pubsub import put_into_leader as _put_into_leader
from pioreactor.web.app import query_app_db
from pioreactor.web.plugin_registry import registered_mcp_tools
from pioreactor.web.utils import is_valid_unix_filename
from pioreactor.whoami import UNIVERSAL_IDENTIFIER


logger = logging.getLogger("mcp_utils")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


MCP_APP_NAME = "pioreactor_mcp"
MCP_VERSION = "0.2.0"
INSTRUCTIONS = """
Use this MCP server to control a Pioreactor cluster of workers. Basic summary:
 - a leader Pioreactor controls multiple worker Pioreactors (the leader can also be a worker)
 - workers should be assigned to an experiment and be "active" before running jobs
 - jobs have settings, some of which can be modified in real-time
 - experiment profiles can be used to run sequences of jobs automatically
"""


def wrap_result_as_dict(func: Callable[..., object]) -> Callable[..., dict[str, object]]:
    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> dict[str, object]:
        result = func(*args, **kwargs)
        return result if isinstance(result, dict) else {"result": result}

    return wrapper


mcp = MCPServer(MCP_APP_NAME, MCP_VERSION, response_queue=SQLiteResponseQueue(), instructions=INSTRUCTIONS)


def _normalize_options(
    options: dict[str, Any] | str | None, *, job_or_action: str | None = None
) -> dict[str, Any]:
    if options is None:
        return {}

    if isinstance(options, dict):
        return options

    if isinstance(options, str):
        try:
            parsed = json.loads(options)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"`options` for {job_or_action or 'this job'} must be a dict or a JSON object string. "
                f'Example: {{"target-rpm": 500}}'
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError(
                f"`options` for {job_or_action or 'this job'} must decode to a JSON object. "
                f'Example: {{"target-rpm": 500}}'
            )

        return cast(dict[str, Any], parsed)

    raise ValueError(
        f"`options` for {job_or_action or 'this job'} must be a dict or a JSON object string, "
        f"got {type(options).__name__}."
    )


def _get_exports_dir() -> Path:
    return Path(os.environ["RUN_PIOREACTOR"]) / "exports"


def _build_export_artifact_response(filename: str) -> dict[str, Any]:
    export_path = _get_exports_dir() / filename
    artifact = {
        "artifact_id": filename,
        "filename": filename,
        "mime_type": "application/zip",
        "download_path": f"/mcp/artifacts/exports/{filename}",
        "leader_local_path": export_path.as_posix(),
    }
    if export_path.exists():
        artifact["size_bytes"] = export_path.stat().st_size  # type: ignore

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
    allow_empty_content: bool = False,
    unwrap_task_result: bool = False,
) -> dict[str, Any]:
    try:
        response = request_fn(endpoint, json=json) if json is not None else request_fn(endpoint)
        response.raise_for_status()

        if allow_empty_content and not response.content:
            content: dict[str, Any] = {}
        else:
            content = cast(dict[str, Any], response.json())

        if response.status_code == 202 and "result_url_path" in content:
            sleep(0.25)
            return get_from_leader(content["result_url_path"])

        if unwrap_task_result and response.status_code == 200 and "task_id" in content:
            if content.get("status") == "succeeded":
                return cast(dict[str, Any], content["result"])
            if content.get("status") == "failed":
                raise HTTPException(content.get("error") or f"Task at {endpoint} failed.")
            raise HTTPException(f"Unexpected task status {content.get('status')} for {endpoint}.")

        if method == "GET" and response.status_code != 200:
            raise HTTPException(f"Unexpected status code {response.status_code} for GET {endpoint}.")

        return content

    except HTTPException as e:
        logger.error(f"Failed to {method} {'from' if method in {'GET', 'DELETE'} else 'into'} leader: {e}")
        raise


def get_from_leader(endpoint: str) -> dict[str, Any]:
    """Wrapper around `get_from_leader` to handle errors and callback checks."""
    return _request_into_leader("GET", endpoint, _get_from_leader, unwrap_task_result=True)


def post_into_leader(endpoint: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrapper around `post_into_leader` to handle errors."""
    return _request_into_leader("POST", endpoint, _post_into_leader, json=json)


def patch_into_leader(endpoint: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrapper around `patch_into_leader` to handle errors."""
    return _request_into_leader("PATCH", endpoint, _patch_into_leader, json=json)


def put_into_leader(endpoint: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrapper around `put_into_leader` to handle errors."""
    return _request_into_leader("PUT", endpoint, _put_into_leader, json=json, allow_empty_content=True)


def delete_from_leader(endpoint: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrapper around `delete_from_leader` to handle errors."""
    return _request_into_leader("DELETE", endpoint, _delete_from_leader, json=json, allow_empty_content=True)


@mcp.tool()
@wrap_result_as_dict
def get_experiments(active_only: bool) -> dict[str, Any]:
    """
    List experiments (name, creation timestamp, description, hours since creation).

    If active_only, list experiments with at least one active worker assigned.
    """
    if active_only:
        return get_from_leader("/api/experiments/active")
    else:
        return get_from_leader("/api/experiments")


@mcp.tool()
@wrap_result_as_dict
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


@mcp.tool()
@wrap_result_as_dict
def get_pioreactor_workers(active_only: bool) -> list[dict[str, Any]]:
    """
    Return the worker inventory with experiment assignments. If *active_only*, filter by `is_active`.

    Common requests include "list worker assignments", "list pioreactors", "list cluster inventory"
    or "which pioreactors are running experiments".
    """
    workers = cast(list[dict[str, Any]], get_from_leader("/api/workers/assignments"))
    return [w for w in workers if w.get("is_active")] if active_only else [w for w in workers]


@mcp.tool()
@wrap_result_as_dict
def assign_workers_to_experiment(experiment: str, pioreactor_unit: str) -> dict[str, Any]:
    """
    Assign a specific worker to an experiment so it can participate in experiment activities.
    """
    payload = {"pioreactor_unit": pioreactor_unit}
    return put_into_leader(f"/api/experiments/{experiment}/workers", json=payload)


@mcp.tool()
@wrap_result_as_dict
def unassign_worker_from_experiment(experiment: str, pioreactor_unit: str) -> dict[str, Any]:
    """
    Remove a worker from an experiment and stop any jobs scoped to that experiment on the worker.
    """
    return delete_from_leader(f"/api/experiments/{experiment}/workers/{pioreactor_unit}")


def _condense_capabilities(capabilities: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Condense capabilities to a summary format with job name, automation name (if any),
    and lists of argument and option names.
    """
    condensed_caps: list[dict[str, Any]] = []

    if capabilities is None:
        return condensed_caps

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


def _summarize_capabilities(capabilities: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Return a slimmer, invocation-focused capability summary.

    This intentionally drops verbose descriptor internals while keeping enough
    information to understand what can be run and how.
    """
    summarized_caps: list[dict[str, Any]] = []

    if capabilities is None:
        return summarized_caps

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


@mcp.tool()
@wrap_result_as_dict
def get_pioreactor_unit_capabilties(pioreactor_unit: str, condensed: bool = False) -> dict[str, Any]:
    """
    List all `pio run` subcommands and their args/options, and published settings.

    If condensed is True, return a summary of each capability including only
    the job name, automation name (if any), and lists of argument and option names.
    Otherwise, return a slimmer invocation-focused summary instead of the raw verbose descriptors.
    """
    caps = cast(
        dict[str, list[dict[str, Any]]], get_from_leader(f"/api/units/{pioreactor_unit}/capabilities")
    )
    if condensed:
        return {unit_: _condense_capabilities(caps_) for unit_, caps_ in caps.items()}
    return {unit_: _summarize_capabilities(caps_) for unit_, caps_ in caps.items()}


@mcp.tool()
def run_job_or_action_on_pioreactor_unit(
    pioreactor_unit: str,
    job_or_action: str,
    experiment: str,
    options: Dict[str, Any] | str | None = None,
    arguments: List[str] | None = None,
) -> dict[str, Any]:
    """
    Launch an action or job on a *pioreactor_unit/worker* within *experiment*.

    This runs `pio run` with the specified job or action name, options, and arguments on the unit(s).

    Parameters:
        pioreactor_unit: target unit name (or "$broadcast" to address all units assigned to the experiment).
        job_or_action: name of the job to run. See `get_unit_capabilties` for all jobs and moreHo .
        experiment: experiment identifier under which to launch the job.
        options: dict of job-specific options, flags, or selectors for the job entry-point. You can also provide a JSON object string.
        args: list of required positional arguments for the job entry-point.
    """
    payload = {
        "options": _normalize_options(options, job_or_action=job_or_action),
        "args": arguments or [],
        "env": {"JOB_SOURCE": "mcp"},
        "config_overrides": [],
    }
    return post_into_leader(
        f"/api/workers/{pioreactor_unit}/jobs/run/job_name/{job_or_action}/experiments/{experiment}",
        json=payload,
    )


@mcp.tool()
def export_experiment_data(
    experiments: list[str],
    dataset_names: list[str],
    partition_by_unit: bool = False,
    partition_by_experiment: bool = True,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, Any]:
    """
    Export datasets from the leader database and return a retrievable artifact handle.

    The returned `download_path` can be fetched from this MCP server, and `leader_local_path`
    points to where the file was written on the leader.
    """
    response = post_into_leader(
        "/api/datasets/exportable/export",
        json={
            "datasets": dataset_names,
            "experiments": experiments,
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
    Target all units with "$broadcast".
    """
    return patch_into_leader(
        f"/api/workers/{pioreactor_unit}/jobs/update/job_name/{job}/experiments/{experiment}",
        json={"settings": settings},
    )


@mcp.tool()
def stop_job_on_pioreactor_unit(
    experiment: str, job: str | None, pioreactor_unit: str = UNIVERSAL_IDENTIFIER
) -> dict[str, Any]:
    """
    Stop running jobs. If `job` parameter is None, stop all jobs associated the experiment for the unit.
    Use the unit param to scope to individual units, or all units in the experiment.

    Users may say "stop all jobs", "stop job <job> in <experiment>", "stop unit <unit> jobs",
    or "stop all jobs in experiment <experiment>".
    """
    if job is None:
        return post_into_leader(f"/api/workers/{pioreactor_unit}/jobs/stop/experiments/{experiment}")
    else:
        return post_into_leader(
            f"/api/workers/{pioreactor_unit}/jobs/stop/job_name/{job}/experiments/{experiment}"
        )


@mcp.tool()
@wrap_result_as_dict
def get_jobs_running_on_pioreactor_unit(pioreactor_unit: str) -> dict[str, Any]:
    """
    Return list of running jobs on *unit/worker*.
    Target all units with "$broadcast".
    """
    return get_from_leader(f"/api/workers/{pioreactor_unit}/jobs/running")


@mcp.tool()
@wrap_result_as_dict
def get_recent_experiment_logs(experiment: str, lines: int = 50) -> dict[str, Any]:
    """
    Tail the last `lines` of logs for a given experiment.
    """
    return get_from_leader(f"/api/experiments/{experiment}/recent_logs?lines={lines}")


@mcp.tool()
def blink_pioreactor_unit(pioreactor_unit: str) -> dict[str, Any]:
    """
    Blink the onboard blue LED of a specific unit.
    Target all units with "$broadcast".
    """
    return post_into_leader(f"/api/workers/{pioreactor_unit}/blink")


@mcp.tool()
def reboot_pioreactor_unit(pioreactor_unit: str) -> dict[str, Any]:
    """
    Reboot/restart a specific unit/worker.
    Target all units with "$broadcast".

    """
    return post_into_leader(f"/api/units/{pioreactor_unit}/system/reboot")


@mcp.tool()
def shutdown_pioreactor_unit(pioreactor_unit: str) -> dict[str, Any]:
    """
    Shutdown a specific unit/worker.
    Target all units with "$broadcast".
    """
    return post_into_leader(f"/api/units/{pioreactor_unit}/system/shutdown")


@mcp.tool()
@wrap_result_as_dict
def get_current_job_settings_for_pioreactor_unit(
    pioreactor_unit: str, job_name: str, experiment: str
) -> dict[str, Any]:
    """
    List settings for a job on a unit/worker.

    Target all units with "$broadcast".
    """
    return get_from_leader(
        f"/api/workers/{pioreactor_unit}/jobs/settings/job_name/{job_name}/experiments/{experiment}"
    )


@mcp.tool()
@wrap_result_as_dict
def get_experiment_profiles() -> dict[str, Any]:
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

    Execute an experiment profile on a unit/worker within an experiment.
    """
    options = {"dry-run": None} if dry_run else {}
    args = ["execute", profile, experiment]
    return run_job_or_action_on_pioreactor_unit(
        get_leader_hostname(), "experiment_profile", experiment, options=options, arguments=args
    )


@mcp.tool()
@wrap_result_as_dict
def db_get_tables() -> list[dict[str, Any]]:
    """List tables in the application database."""
    tables = query_app_db(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    )
    assert isinstance(tables, list)
    return tables


@mcp.tool()
@wrap_result_as_dict
def db_get_table_schema(table_name: str) -> list[dict[str, Any]]:
    """Get schema for the specified table."""
    exists = query_app_db("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
    if not exists:
        raise ValueError(f"Table '{table_name}' does not exist in the database.")
    schema = query_app_db(f"PRAGMA table_info('{table_name}');")
    assert isinstance(schema, list)
    return schema


@mcp.tool()
@wrap_result_as_dict
def db_query_db(query: str) -> list[dict[str, Any]]:
    """Read-only query the database."""
    rows = query_app_db(query)
    assert isinstance(rows, list)
    return rows


@mcp.tool()
def get_pioreactor_unit_configuration(pioreactor_unit: str) -> dict[str, Any]:
    """Get merged configuration for a given unit from shared config.ini plus the unit's local unit_config.ini."""
    return get_from_leader(f"/api/config/units/{pioreactor_unit}")


for tool, kwargs in registered_mcp_tools():
    mcp.tool(**kwargs)(tool)


mcp_bp = Blueprint("mcp", __name__, url_prefix="/mcp")


@mcp_bp.post("/")
def handle_mcp() -> Response:
    payload = request.get_json(force=True, silent=False)

    result = mcp.handle_message(payload)
    if result:
        return jsonify(msgspec.to_builtins(result))
    else:
        return Response(status=202)


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
