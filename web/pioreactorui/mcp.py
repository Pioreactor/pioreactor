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


def get_from_leader(endpoint: str) -> dict:
    """Wrapper around `get_from_leader` to handle errors and callback checks."""
    logger.debug(endpoint)
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
            return r.json()
        else:
            raise HTTPException(f"Unexpected status code {r.status_code} for GET {endpoint}: {r.content}")
    except HTTPException as e:
        logger.error(f"Failed to GET from leader: {e}")
        raise


def post_into_leader(endpoint: str, json: dict | None = None) -> dict:
    """Wrapper around `post_into_leader` to handle errors."""
    logger.debug(endpoint, json)
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
    logger.debug(endpoint, json)
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
def list_experiments() -> dict:
    """List all experiments (name, creation timestamp, description, hours since creation)."""
    return get_from_leader("/api/experiments")


@mcp.tool()
def list_workers(active_only: bool) -> dict:
    """Return the cluster inventory. If *active_only*, filter by `is_active`."""
    workers = get_from_leader("/api/workers")
    return {"workers": [w for w in workers if w.get("is_active")] if active_only else workers}


@mcp.tool()
def list_workers_experiment_assignments(active_only: bool) -> dict:
    """Return the cluster inventory with experiment assignments. If *active_only*, filter by `is_active`."""
    workers = get_from_leader("/api/workers/assignments")
    return {"workers": [w for w in workers if w.get("is_active")] if active_only else workers}


@mcp.tool()
def list_jobs_available(unit: str) -> dict:
    """Return the unit's available jobs that can be run and settings that can be viewed or changed. Can use "$broadcast" for all units."""
    return get_from_leader(f"/api/units/{unit}/jobs/discover")


@mcp.tool()
def run_job(
    unit: str,
    job: str,
    experiment: str,
    options: Dict[str, Any] | None = None,
    args: List[str] | None = None,
    env: Dict[str, str] | None = None,
    config_overrides: List[List[str]] | None = None,
) -> dict:
    """Launch *job* on *unit* within *experiment* via leader REST API. Can use "$broadcast" for all units."""
    payload = {
        "options": options or {},
        "args": args or [],
        "env": env or {},
        "config_overrides": config_overrides or [],
    }
    return post_into_leader(
        f"/api/workers/{unit}/jobs/run/job_name/{job}/experiments/{experiment}",
        json=payload,
    )


@mcp.tool()
def update_job(unit: str, job: str, experiment: str, settings: dict[str, Any]) -> dict:
    """Update settings for a job on a unit within an experiment.  Can use "$broadcast" for all units."""
    return patch_into_leader(
        f"/api/workers/{unit}/jobs/update/job_name/{job}/experiments/{experiment}",
        json={"settings": settings},
    )


@mcp.tool()
def stop_job(unit: str, job: str, experiment: str) -> dict:
    """Stop *job* on *unit*; optionally scope to *experiment*. Can use "$broadcast" for all units."""
    endpoint = f"/api/workers/{unit}/jobs/stop/job_name/{job}/experiments/{experiment}"
    return post_into_leader(endpoint)


@mcp.tool()
def stop_all_jobs_in_experiment(experiment: str) -> dict:
    """Stop all jobs across the cluster for a given experiment. Can use "$broadcast" for all units."""
    return post_into_leader(f"/api/workers/jobs/stop/experiments/{experiment}")


@mcp.tool()
def stop_all_jobs_on_unit(unit: str, experiment: str) -> dict:
    """Stop all jobs on a specific unit for a given experiment. Can use "$broadcast" for all units."""
    return post_into_leader(f"/api/workers/{unit}/jobs/stop/experiments/{experiment}")


@mcp.tool()
def running_jobs(unit: str) -> dict:
    """Return list of running jobs on *unit*. Can use "$broadcast" for all units."""
    return get_from_leader(f"/api/workers/{unit}/jobs/running")


@mcp.tool()
def get_recent_experiment_logs(experiment: str, lines: int = 50) -> dict:
    """Tail the last `lines` of logs for a given experiment."""
    return get_from_leader(f"/api/experiments/{experiment}/recent_logs?lines={lines}")


@mcp.tool()
def blink(unit: str) -> dict:
    """Blink the LED of a specific unit. Can use "$broadcast" for all units."""
    return post_into_leader(f"/api/workers/{unit}/blink")


@mcp.tool()
def reboot_unit(unit: str) -> dict:
    """Reboot a specific unit. Can use "$broadcast" for all units."""
    return post_into_leader(f"/api/units/{unit}/system/reboot")


@mcp.tool()
def shutdown_unit(unit: str) -> dict:
    """Shutdown a specific unit. Can use "$broadcast" for all units."""
    return post_into_leader(f"/api/units/{unit}/system/shutdown")


@mcp.tool()
def running_jobs_experiment(experiment: str) -> dict:
    """List running jobs for a given experiment across all units."""
    return get_from_leader(f"/api/experiments/{experiment}/jobs/running")


@mcp.tool()
def running_jobs_unit_experiment(unit: str, experiment: str) -> dict:
    """List running jobs on a specific unit within an experiment. Can use "$broadcast" for all units."""
    return get_from_leader(f"/api/workers/{unit}/experiments/{experiment}/jobs/running")


@mcp.tool()
def get_od_readings(experiment: str, filter_mod_N: float = 100.0, lookback: float = 4.0) -> dict:
    """Get filtered OD vs time readings for all units in an experiment."""
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/od_readings?filter_mod_N={filter_mod_N}&lookback={lookback}"
    )


@mcp.tool()
def get_growth_rates(experiment: str, filter_mod_N: float = 100.0, lookback: float = 4.0) -> dict:
    """Get filtered growth rate vs time readings for all units in an experiment."""
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/growth_rates?filter_mod_N={filter_mod_N}&lookback={lookback}"
    )


@mcp.tool()
def get_temperature_readings(experiment: str, lookback: float = 4.0) -> dict:
    """Get temperature vs time readings for all units in an experiment."""
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/temperature_readings?lookback={lookback}"
    )


@mcp.tool()
def get_od_readings_filtered(experiment: str, filter_mod_N: float = 100.0, lookback: float = 4.0) -> dict:
    """Get filtered OD vs time readings for all units in an experiment."""
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/od_readings_filtered?filter_mod_N={filter_mod_N}&lookback={lookback}"
    )


@mcp.tool()
def get_raw_od_readings(experiment: str, lookback: float = 4.0) -> dict:
    """Get raw OD vs time readings for all units in an experiment."""
    return get_from_leader(f"/api/experiments/{experiment}/time_series/raw_od_readings?lookback={lookback}")


@mcp.tool()
def get_time_series_column(experiment: str, data_source: str, column: str, lookback: float = 4.0) -> dict:
    """Get a specific time-series column for all units in an experiment."""
    return get_from_leader(
        f"/api/experiments/{experiment}/time_series/{data_source}/{column}?lookback={lookback}"
    )


@mcp.tool()
def list_config_inis() -> dict:
    """List available config.ini files (global and unit-specific)."""
    return get_from_leader("/api/configs")


@mcp.tool()
def get_config_ini(filename: str) -> dict:
    """Retrieve the contents of a specific config.ini file."""
    return get_from_leader(f"/api/configs/{filename}")


@mcp.tool()
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
