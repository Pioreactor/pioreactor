# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import sys
from functools import wraps
from time import sleep
from typing import Any
from typing import Dict
from typing import List

import msgspec
from flask import Blueprint
from flask import jsonify
from flask import request
from flask import Response
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


def wrap_result_as_dict(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return result if isinstance(result, dict) else {"result": result}

    return wrapper


mcp = MCPServer(MCP_APP_NAME, MCP_VERSION, response_queue=SQLiteResponseQueue(), instructions=INSTRUCTIONS)


def get_from_leader(endpoint: str) -> dict:
    """Wrapper around `get_from_leader` to handle errors and callback checks."""
    try:
        r = _get_from_leader(endpoint)
        r.raise_for_status()

        content = r.json()
        if r.status_code == 202 and "result_url_path" in content:
            # task not completed yet, try again recursively
            sleep(0.25)
            # get the url
            return get_from_leader(content["result_url_path"])

        elif r.status_code == 200:
            if "task_id" in r.json():
                # result of a delayed response - just provide the result to reduce noise.
                return r.json()["result"]
            else:
                return r.json()
        else:
            raise HTTPException(f"Unexpected status code {r.status_code} for GET {endpoint}.")
    except HTTPException as e:
        logger.error(f"Failed to GET from leader: {e}")
        raise


def post_into_leader(endpoint: str, json: dict | None = None) -> dict:
    """Wrapper around `post_into_leader` to handle errors."""
    try:
        r = _post_into_leader(endpoint, json=json)
        r.raise_for_status()
        content = r.json()
        if r.status_code == 202 and "result_url_path" in content:
            sleep(0.25)
            return get_from_leader(content["result_url_path"])
        else:
            return content

    except HTTPException as e:
        logger.error(f"Failed to POST into leader: {e}")
        raise


def patch_into_leader(endpoint: str, json: dict | None = None) -> dict:
    """Wrapper around `patch_into_leader` to handle errors."""
    try:
        r = _patch_into_leader(endpoint, json=json)
        r.raise_for_status()
        content = r.json()
        if r.status_code == 202 and "result_url_path" in content:
            sleep(0.25)
            return get_from_leader(content["result_url_path"])
        else:
            return content

    except HTTPException as e:
        logger.error(f"Failed to PATCH into leader: {e}")
        raise


def put_into_leader(endpoint: str, json: dict | None = None) -> dict:
    """Wrapper around `put_into_leader` to handle errors."""
    try:
        r = _put_into_leader(endpoint, json=json)
        r.raise_for_status()
        content = r.json() if r.content else {}
        if r.status_code == 202 and "result_url_path" in content:
            sleep(0.25)
            return get_from_leader(content["result_url_path"])
        else:
            return content

    except HTTPException as e:
        logger.error(f"Failed to PUT into leader: {e}")
        raise


def delete_from_leader(endpoint: str, json: dict | None = None) -> dict:
    """Wrapper around `delete_from_leader` to handle errors."""
    try:
        r = _delete_from_leader(endpoint, json=json)
        r.raise_for_status()
        content = r.json() if r.content else {}
        if r.status_code == 202 and "result_url_path" in content:
            sleep(0.25)
            return get_from_leader(content["result_url_path"])
        else:
            return content

    except HTTPException as e:
        logger.error(f"Failed to DELETE from leader: {e}")
        raise


@mcp.tool()
@wrap_result_as_dict
def get_experiments(active_only: bool) -> dict:
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
) -> dict:
    """
    Create a new experiment record with optional metadata about media and organism.
    """
    payload: dict[str, str] = {"experiment": experiment}
    if description is not None:
        payload["description"] = description
    return post_into_leader("/api/experiments", json=payload)


@mcp.tool()
@wrap_result_as_dict
def get_pioreactor_workers(active_only: bool) -> list:
    """
    Return the worker inventory with experiment assignments. If *active_only*, filter by `is_active`.

    Common requests include "list worker assignments", "list pioreactors", "list cluster inventory"
    or "which pioreactors are running experiments".
    """
    workers = get_from_leader("/api/workers/assignments")
    return [w for w in workers if w.get("is_active")] if active_only else [w for w in workers]


@mcp.tool()
@wrap_result_as_dict
def assign_workers_to_experiment(experiment: str, pioreactor_unit: str) -> dict:
    """
    Assign a specific worker to an experiment so it can participate in experiment activities.
    """
    payload = {"pioreactor_unit": pioreactor_unit}
    return put_into_leader(f"/api/experiments/{experiment}/workers", json=payload)


@mcp.tool()
@wrap_result_as_dict
def unassign_worker_from_experiment(experiment: str, pioreactor_unit: str) -> dict:
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


@mcp.tool()
@wrap_result_as_dict
def get_pioreactor_unit_capabilties(pioreactor_unit: str, condensed: bool = False) -> dict:
    """
    List all `pio run` subcommands and their args/options, and published settings.

    If condensed is True, return a summary of each capability including only
    the job name, automation name (if any), and lists of argument and option names.
    """
    caps = get_from_leader(f"/api/units/{pioreactor_unit}/capabilities")
    return caps if not condensed else {unit_: _condense_capabilities(caps_) for unit_, caps_ in caps.items()}


@mcp.tool()
def run_job_or_action_on_pioreactor_unit(
    pioreactor_unit: str,
    job_or_action: str,
    experiment: str,
    options: Dict[str, Any] | None = None,
    arguments: List[str] | None = None,
) -> dict:
    """
    Launch an action or job on a *pioreactor_unit/worker* within *experiment*.

    This runs `pio run` with the specified job or action name, options, and arguments on the unit(s).

    Parameters:
        pioreactor_unit: target unit name (or "$broadcast" to address all units assigned to the experiment).
        job_or_action: name of the job to run. See `get_unit_capabilties` for all jobs and moreHo .
        experiment: experiment identifier under which to launch the job.
        options: dict of job-specific options, flags, or selectors for the job entry-point. You probably want to use this over args.
        args: list of required positional arguments for the job entry-point.
    """
    payload = {
        "options": options or {},
        "args": arguments or [],
        "env": {"JOB_SOURCE": "mcp"},
        "config_overrides": [],
    }
    return post_into_leader(
        f"/api/workers/{pioreactor_unit}/jobs/run/job_name/{job_or_action}/experiments/{experiment}",
        json=payload,
    )


@mcp.tool()
def update_pioreactor_unit_job_settings(
    pioreactor_unit: str, job: str, experiment: str, settings: dict[str, Any]
) -> dict:
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
) -> dict:
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
def get_jobs_running_on_pioreactor_unit(pioreactor_unit: str) -> dict:
    """
    Return list of running jobs on *unit/worker*.
    Target all units with "$broadcast".
    """
    return get_from_leader(f"/api/workers/{pioreactor_unit}/jobs/running")


@mcp.tool()
@wrap_result_as_dict
def get_recent_experiment_logs(experiment: str, lines: int = 50) -> dict:
    """
    Tail the last `lines` of logs for a given experiment.
    """
    return get_from_leader(f"/api/experiments/{experiment}/recent_logs?lines={lines}")


@mcp.tool()
def blink_pioreactor_unit(pioreactor_unit: str) -> dict:
    """
    Blink the onboard blue LED of a specific unit.
    Target all units with "$broadcast".
    """
    return post_into_leader(f"/api/workers/{pioreactor_unit}/blink")


@mcp.tool()
def reboot_pioreactor_unit(pioreactor_unit: str) -> dict:
    """
    Reboot/restart a specific unit/worker.
    Target all units with "$broadcast".

    """
    return post_into_leader(f"/api/units/{pioreactor_unit}/system/reboot")


@mcp.tool()
def shutdown_pioreactor_unit(pioreactor_unit: str) -> dict:
    """
    Shutdown a specific unit/worker.
    Target all units with "$broadcast".
    """
    return post_into_leader(f"/api/units/{pioreactor_unit}/system/shutdown")


@mcp.tool()
@wrap_result_as_dict
def get_current_job_settings_for_pioreactor_unit(
    pioreactor_unit: str, job_name: str, experiment: str
) -> dict:
    """
    List settings for a job on a unit/worker.

    Target all units with "$broadcast".
    """
    return get_from_leader(
        f"/api/workers/{pioreactor_unit}/jobs/settings/job_name/{job_name}/experiments/{experiment}"
    )


@mcp.tool()
@wrap_result_as_dict
def get_experiment_profiles() -> dict:
    """
    Profiles are pre-defined "scripts" that execute commands as certain times (like a recipe.)

    List available experiment profiles (filename, fullpath, and parsed metadata).
    """
    return get_from_leader("/api/contrib/experiment_profiles")


@mcp.tool()
def run_experiment_profile(
    profile: str,
    experiment: str,
    dry_run: bool = False,
) -> dict:
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
def db_get_tables() -> list:
    """List tables in the application database."""
    tables = query_app_db(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    )
    assert isinstance(tables, list)
    return tables


@mcp.tool()
@wrap_result_as_dict
def db_get_table_schema(table_name: str) -> list:
    """Get schema for the specified table."""
    exists = query_app_db("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
    if not exists:
        raise ValueError(f"Table '{table_name}' does not exist in the database.")
    schema = query_app_db(f"PRAGMA table_info('{table_name}');")
    assert isinstance(schema, list)
    return schema


@mcp.tool()
@wrap_result_as_dict
def db_query_db(query: str) -> list:
    """Read-only query the database."""
    rows = query_app_db(query)
    assert isinstance(rows, list)
    return rows


@mcp.tool()
def get_pioreactor_unit_configuration(pioreactor_unit: str) -> dict:
    """Get merged configuration for a given unit (global config.ini and unit-specific unit_config.ini)."""
    return get_from_leader(f"/api/units/{pioreactor_unit}/configuration")


for tool, kwargs in registered_mcp_tools():
    mcp.tool(**kwargs)(tool)


mcp_bp = Blueprint("mcp", __name__, url_prefix="/mcp")


@mcp_bp.post("/")
def handle_mcp():
    payload = request.get_json(force=True, silent=False)

    result = mcp.handle_message(payload)
    if result:
        return jsonify(msgspec.to_builtins(result))
    else:
        return Response(status=202)
