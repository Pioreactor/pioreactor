# -*- coding: utf-8 -*-
"""
Pioreactor MCP **blueprint**
==========================

This module defines a Flask *Blueprint* exposing an [Model‑Context‑Protocol](/) entry‑point that
wraps a handful of Pioreactor operations as MCP tools. The blueprint can be
registered inside the **leader** web app next to the existing `api` and
`unit_api` blueprints:

```python
from pioreactorui.mcp_blueprint import mcp_bp

if am_I_leader():
    app.register_blueprint(api)
    app.register_blueprint(mcp_bp)  # <— this file
```

Running it standalone for local testing is still possible (`python mcp_blueprint.py`).
"""
from __future__ import annotations

import logging
import os
import sys
from functools import wraps
from queue import Empty
from queue import Queue
from time import sleep
from typing import Any
from typing import Dict
from typing import List

from flask import Blueprint
from flask import Flask
from flask import jsonify
from flask import request
from mcp_utils.core import MCPServer
from mcp_utils.queue import ResponseQueueProtocol
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import get_from_leader as _get_from_leader
from pioreactor.pubsub import patch_into_leader as _patch_into_leader
from pioreactor.pubsub import post_into_leader as _post_into_leader

logger = logging.getLogger("mcp_utils")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


def wrap_result_as_dict(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return result if isinstance(result, dict) else {"result": result}

    return wrapper


class ResponseQueue(ResponseQueueProtocol):
    def __init__(self) -> None:
        self.queues: dict[str, Queue] = {}

    def push_response(self, session_id: str, response) -> None:
        if session_id not in self.queues:
            self.queues[session_id] = Queue()
        self.queues[session_id].put(response.model_dump_json())

    def wait_for_response(self, session_id: str, timeout: float | None = None) -> str | None:
        if session_id not in self.queues:
            return None
        try:
            return self.queues[session_id].get(timeout=timeout)
        except Empty:
            return None

    def clear_session(self, session_id: str) -> None:
        if session_id in self.queues:
            del self.queues[session_id]


MCP_APP_NAME = "pioreactor_mcp"
MCP_VERSION = "0.1.0"

mcp = MCPServer(MCP_APP_NAME, MCP_VERSION, response_queue=ResponseQueue())


def get_from_leader(endpoint: str):
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


def post_into_leader(endpoint: str, json: dict | None = None):
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


# ---------------------------------------------------------------------------
# MCP **tools** (thin wrappers around existing REST routes)
# ---------------------------------------------------------------------------
@mcp.tool()
@wrap_result_as_dict
def list_experiments() -> dict:
    """
    List all experiments (name, creation timestamp, description, hours since creation).

    Users may ask for this tool with phrases like "list experiments", "show experiments",
    or "get experiments" when interacting via MCP.
    """
    return get_from_leader("/api/experiments")


@mcp.tool()
@wrap_result_as_dict
def list_active_experiments() -> list:
    """
    List experiments with at least one active worker assigned.

    Users may ask "list active experiments", "get experiments", etc.
    """
    return get_from_leader("/api/experiments/active")


@mcp.tool()
@wrap_result_as_dict
def list_workers(active_only: bool) -> list:
    """
    Return the cluster inventory (aka workers). If *active_only*, filter by `is_active`.

    Users might phrase this as "list pioreactors", "show units", "get worker list",
    or ask "which units are active" through the MCP interface.
    """
    workers = get_from_leader("/api/workers")
    return [w for w in workers if w.get("is_active")] if active_only else workers


@mcp.tool()
@wrap_result_as_dict
def list_workers_experiment_assignments(active_only: bool) -> list:
    """
    Return the cluster inventory with experiment assignments. If *active_only*, filter by `is_active`.

    Common requests include "list worker assignments", "show experiment assignments",
    or "which pioreactors are running experiments" via MCP.
    """
    workers = get_from_leader("/api/workers/assignments")
    return [w for w in workers if w.get("is_active")] if active_only else workers


@mcp.tool()
@wrap_result_as_dict
def discover_actions_available(unit: str) -> list:
    """
    List all `pio run` subcommands and their args/options via the leader API.
    """
    return get_from_leader(f"/api/units/{unit}/actions/discover")


@mcp.tool()
@wrap_result_as_dict
def discover_published_settings_in_jobs(unit: str) -> dict:
    """
    Return the unit/worker's jobs that can be run and settings that can be viewed or changed.

    Users may ask "what jobs can I run" or "list available jobs and settings", optionally using
    "$broadcast" to query all units at once.
    """
    return get_from_leader(f"/api/units/{unit}/jobs/discover")


@mcp.tool()
def run_job(
    unit: str,
    job: str,
    experiment: str,
    options: Dict[str, Any] | None = None,
    args: List[str] | None = None,
    config_overrides: List[List[str]] | None = None,
) -> dict:
    """
    Launch *job* on a *unit/worker* within *experiment* via the leader REST API.

    Users might say "run job", "start <job> on worker <unit>".
    Use "$broadcast" to start jobs across all units simultaneously in that experiment.

    Parameters:
        unit: target unit name (or "$broadcast" to address all units).
        job: name of the job to run. See `list_jobs_available` for options.
        experiment: experiment identifier under which to launch the job.
        options: dict of job-specific options for the job entrypoint.
        args: list of positional arguments for the job entrypoint.
        config_overrides: list of [<section.key>, <value>] pairs to override config settings.
    """
    payload = {
        "options": options or {},
        "args": args or [],
        "env": {"JOB_SOURCE": "mcp"},
        "config_overrides": config_overrides or [],
    }
    return post_into_leader(
        f"/api/workers/{unit}/jobs/run/job_name/{job}/experiments/{experiment}",
        json=payload,
    )


@mcp.tool()
def update_job_settings(unit: str, job: str, experiment: str, settings: dict[str, Any]) -> dict:
    """
    Update the active job settings for a job on a unit/worker within an experiment.

    Common phrases include "update job <job> to <settings>", "change <setting> in <job>",
    or "set parameters of <job>", with "$broadcast" supported for all units.

    See `list_jobs_available` for jobs and their settings.
    """
    return patch_into_leader(
        f"/api/workers/{unit}/jobs/update/job_name/{job}/experiments/{experiment}",
        json={"settings": settings},
    )


@mcp.tool()
def stop_job(unit: str, job: str, experiment: str) -> dict:
    """
    Stop *job* on *unit/worker*; optionally scope to *experiment*.

    Users may request "stop job", "kill <job>", or "end job",
    with "$broadcast" available to stop jobs on all units.
    """
    endpoint = f"/api/workers/{unit}/jobs/stop/job_name/{job}/experiments/{experiment}"
    return post_into_leader(endpoint)


@mcp.tool()
def stop_all_jobs_in_experiment(experiment: str) -> dict:
    """
    Stop all jobs across the cluster for a given experiment.

    This tool may be invoked as "stop all jobs", "abort experiment jobs",
    or "terminate experiment <name>"; "$broadcast" works for all units.
    """
    return post_into_leader(f"/api/workers/jobs/stop/experiments/{experiment}")


@mcp.tool()
def stop_all_jobs_on_unit(unit: str, experiment: str) -> dict:
    """
    Stop all jobs on a specific unit/worker for a given experiment.

    Users might say "stop unit jobs", "end all jobs on <unit>",
    or target all units with "$broadcast".
    """
    return post_into_leader(f"/api/workers/{unit}/jobs/stop/experiments/{experiment}")


@mcp.tool()
@wrap_result_as_dict
def running_jobs(unit: str) -> dict:
    """
    Return list of running jobs on *unit/worker*.

    Common queries include "what jobs are running", "list active jobs",
    or using "$broadcast" to see jobs on all units.
    """
    return get_from_leader(f"/api/workers/{unit}/jobs/running")


@mcp.tool()
@wrap_result_as_dict
def get_recent_experiment_logs(experiment: str, lines: int = 50) -> dict:
    """
    Tail the last `lines` of logs for a given experiment.

    Users may request "show logs", "tail logs", or "get recent logs",
    specifying the number of lines to retrieve.
    """
    return get_from_leader(f"/api/experiments/{experiment}/recent_logs?lines={lines}")


@mcp.tool()
def blink(unit: str) -> dict:
    """
    Blink the LED of a specific unit.

    Common phrases include "blink unit", "flash LED", or "show light",
    with "$broadcast" supported to blink all units.
    """
    return post_into_leader(f"/api/workers/{unit}/blink")


@mcp.tool()
def reboot_unit(unit: str) -> dict:
    """
    Reboot a specific unit/worker.

    Users may command "reboot unit", "restart device", or "restart unit",
    and can use "$broadcast" to reboot all units.
    """
    return post_into_leader(f"/api/units/{unit}/system/reboot")


@mcp.tool()
def shutdown_unit(unit: str) -> dict:
    """
    Shutdown a specific unit/worker.

    Common commands include "shutdown unit", "power off device", or "stop unit",
    with "$broadcast" to shutdown all units if needed.
    """
    return post_into_leader(f"/api/units/{unit}/system/shutdown")


@mcp.tool()
@wrap_result_as_dict
def get_active_job_settings_for_worker(unit: str, job_name: str) -> dict:
    """
    List settings for a job on a unit/worker.

    Users often ask "show job settings", "get settings for <job>",
    or include "$broadcast" to retrieve settings cluster-wide.
    """
    return get_from_leader(f"/api/workers/{unit}/jobs/settings/job_name/{job_name}")


@mcp.tool()
@wrap_result_as_dict
def get_active_settings_for_job_across_cluster_in_experiment(experiment: str, job_name: str) -> dict:
    """
    List settings for a job across the cluster within a given experiment.

    Users may ask "list worker settings for <job>",
    "show global <job> settings", or "get settings for <job> in <experiment>".
    """
    return get_from_leader(f"/api/experiments/{experiment}/jobs/settings/job_name/{job_name}")


@mcp.tool()
@wrap_result_as_dict
def get_od_readings(experiment: str, filter_mod_N: float = 100.0, lookback: float = 4.0) -> dict:
    """
    Get filtered OD vs time readings for all units in an experiment.

    Users may request "get OD readings", "show optical density data",
    or "plot OD vs time" with parameters filter_mod_N and lookback.
    """
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/od_readings?filter_mod_N={filter_mod_N}&lookback={lookback}"
    )


@mcp.tool()
@wrap_result_as_dict
def get_growth_rates(experiment: str, filter_mod_N: float = 100.0, lookback: float = 4.0) -> dict:
    """
    Get filtered growth rate vs time readings for all units in an experiment.

    Common phrases include "get growth rates", "show growth rate data",
    or "plot growth vs time" using filter_mod_N and lookback parameters.
    """
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/growth_rates?filter_mod_N={filter_mod_N}&lookback={lookback}"
    )


@mcp.tool()
@wrap_result_as_dict
def get_temperature_readings(experiment: str, lookback: float = 4.0) -> dict:
    """
    Get temperature vs time readings for all units in an experiment.

    Users may ask "get temperature readings", "show temperature data",
    or "plot temperature vs time" with a specified lookback period.
    """
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/temperature_readings?lookback={lookback}"
    )


@mcp.tool()
@wrap_result_as_dict
def get_od_readings_filtered(experiment: str, filter_mod_N: float = 100.0, lookback: float = 4.0) -> dict:
    """
    Get filtered OD vs time readings for all units in an experiment.

    Similar to get_od_readings but explicitly named 'filtered', users may
    request "filtered OD readings" or "get OD data filtered" by lookback and mod parameters.
    """
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/od_readings_filtered?filter_mod_N={filter_mod_N}&lookback={lookback}"
    )


@mcp.tool()
@wrap_result_as_dict
def get_raw_od_readings(experiment: str, lookback: float = 4.0) -> dict:
    """
    Get raw OD vs time readings for all units in an experiment.

    Users may ask "get raw OD readings" or "show unfiltered optical density data"
    specifying a lookback period.
    """
    return get_from_leader(f"/api/experiments/{experiment}/time_series/raw_od_readings?lookback={lookback}")


@mcp.tool()
@wrap_result_as_dict
def list_experiment_profiles() -> dict:
    """
    List available experiment profiles (filename, fullpath, and parsed metadata).

    Users may request "list profiles", "show experiment templates",
    or "get profile metadata" when preparing experiments.
    """
    return get_from_leader("/api/contrib/experiment_profiles")


@mcp.tool()
def run_experiment_profile(
    unit: str,
    profile: str,
    experiment: str,
    dry_run: bool = False,
) -> dict:
    """
    Execute an experiment profile on a unit/worker within an experiment.

    Common commands include "run profile <profile>", "execute experiment template",
    or "apply profile to <unit>", with a "dry-run" option for simulation.
    """
    options = {"dry-run": None} if dry_run else {}
    args = ["execute", profile, experiment]
    return run_job(unit, "experiment_profile", experiment, options=options, args=args)


# ---------------------------------------------------------------------------
# MCP **tools** for exportable datasets
# ---------------------------------------------------------------------------
@mcp.tool()
@wrap_result_as_dict
def list_exportable_datasets() -> dict:
    """
    List available exportable datasets (dataset_name, description, display_name, etc.).

    Users may ask "list exportable datasets", "show datasets", or "get exportable datasets".
    """
    return get_from_leader("/api/contrib/exportable_datasets")


@mcp.tool()
@wrap_result_as_dict
def preview_exportable_datasets(dataset_name: str, n_rows: int = 5) -> dict:
    """
    Preview rows of an exportable dataset.

    Users may request this tool to see a sample of an exportable dataset, specifying
    the dataset name and number of rows.
    """
    return get_from_leader(f"/api/contrib/exportable_datasets/{dataset_name}/preview?n_rows={n_rows}")


@mcp.tool()
@wrap_result_as_dict
def query_dataset(
    dataset_name: str,
    experiment: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict:
    """
    Query a dataset with optional filters. This returns a JSON object with a path to download the csv/zip.

    Users may specify experiment, time bounds (iso 8601) to filter the dataset.
    """
    payload: Dict[str, list[str] | str | bool] = {"datasets": [dataset_name]}
    if experiment:
        payload["experiments"] = [experiment]
    if start_time:
        payload["start_time"] = start_time
    if end_time:
        payload["end_time"] = end_time

    payload["partition_by_unit"] = False
    payload["partition_by_experiment"] = False

    # ask leader to export datasets (returns JSON with `filename` and `msg`)
    return post_into_leader("/api/contrib/exportable_datasets/export_datasets", json=payload)


# MCP **resources** for config: list of config.ini files, config contents, and unit configuration
# ---------------------------------------------------------------------------
@mcp.resource(path="configs", name="list_config_inis")
def list_config_inis() -> dict:
    """List available config.ini files (global and unit-specific)."""
    return get_from_leader("/api/configs")


@mcp.resource(path="configs/{filename}", name="get_config_ini")
def get_config_ini(filename: str) -> dict:
    """Retrieve the contents of a specific config.ini file."""
    return get_from_leader(f"/api/configs/{filename}")


@mcp.resource(path="units/{unit}/configuration", name="get_unit_configuration")
def get_unit_configuration(unit: str) -> dict:
    """Get merged configuration for a given unit (global and unit-specific)."""
    return get_from_leader(f"/api/units/{unit}/configuration")


mcp_bp = Blueprint("mcp", __name__, url_prefix="/mcp")


@mcp_bp.post("/")
def handle_mcp():
    payload = request.get_json(force=True, silent=False)
    result = mcp.handle_message(payload)
    return jsonify(result.model_dump(exclude_none=True))


if __name__ == "__main__":

    def _create_dev_app() -> Flask:
        app = Flask(__name__)
        app.register_blueprint(mcp_bp)
        return app

    _create_dev_app().run(host="0.0.0.0", port=int(os.getenv("MCP_PORT", "9040")))
