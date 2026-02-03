# -*- coding: utf-8 -*-
import configparser
import json
import os
import re
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from flask import Response
from flask import send_file
from flask.typing import ResponseReturnValue
from huey.api import Result
from huey.exceptions import HueyException
from huey.exceptions import TaskException
from msgspec import DecodeError
from msgspec import to_builtins
from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from pioreactor import structs
from pioreactor.config import get_leader_hostname
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.models import get_registered_models
from pioreactor.mureq import HTTPErrorStatus
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import get_from
from pioreactor.pubsub import post_into
from pioreactor.structs import CalibrationBase
from pioreactor.structs import Dataset
from pioreactor.utils.networking import resolve_to_address
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.web import tasks
from pioreactor.web.app import client
from pioreactor.web.app import get_all_units
from pioreactor.web.app import get_all_workers
from pioreactor.web.app import get_all_workers_in_experiment
from pioreactor.web.app import HOSTNAME
from pioreactor.web.app import modify_app_db
from pioreactor.web.app import msg_to_JSON
from pioreactor.web.app import publish_to_error_log
from pioreactor.web.app import publish_to_experiment_log
from pioreactor.web.app import publish_to_log
from pioreactor.web.app import query_app_db
from pioreactor.web.app import query_temp_local_metadata_db
from pioreactor.web.plugin_registry import registered_api_routes
from pioreactor.web.utils import abort_with
from pioreactor.web.utils import attach_cache_control
from pioreactor.web.utils import create_task_response
from pioreactor.web.utils import DelayedResponseReturnValue
from pioreactor.web.utils import is_valid_unix_filename
from pioreactor.web.utils import scrub_to_valid
from pioreactor.whoami import is_testing_env
from pioreactor.whoami import UNIVERSAL_EXPERIMENT
from pioreactor.whoami import UNIVERSAL_IDENTIFIER
from werkzeug.utils import safe_join
from werkzeug.utils import secure_filename

AllCalibrations = structs.subclass_union(CalibrationBase)

api_bp = Blueprint("api", __name__, url_prefix="/api")

for rule, options, view_func in registered_api_routes():
    api_bp.add_url_rule(rule, view_func=view_func, **options)


def as_json_response(json: str) -> ResponseReturnValue:
    return Response(json, mimetype="application/json")


def format_utc_timestamp_for_lookback_hours(lookback_hours: float) -> str:
    cutoff = current_utc_datetime() - timedelta(hours=lookback_hours)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _extract_unit_api_error(response: Response | None) -> str | None:
    if response is None:
        return None
    body = response.content
    if not body:
        return None
    content_type = response.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        return None
    try:
        payload = json.loads(body)
    except Exception:
        return None
    if isinstance(payload, dict):
        for key in ("error", "description"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def broadcast_get_across_cluster(endpoint: str, timeout: float = 5.0, return_raw=False) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_get(
        endpoint=endpoint, units=get_all_units(), timeout=timeout, return_raw=return_raw
    )


def broadcast_post_across_cluster(
    endpoint: str,
    json: dict | None = None,
    params: dict | None = None,
    timeout: float = 30.0,
) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_post(endpoint, get_all_units(), json=json, params=params, timeout=timeout)


def broadcast_delete_across_cluster(endpoint: str, json: dict | None = None, timeout: float = 30.0) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_delete(endpoint, get_all_units(), json=json, timeout=timeout)


def broadcast_patch_across_cluster(endpoint: str, json: dict | None = None, timeout: float = 30.0) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_patch(endpoint, get_all_units(), json=json, timeout=timeout)


# send only to workers
def broadcast_get_across_workers(endpoint: str, timeout: float = 5.0, return_raw=False) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_get(
        endpoint=endpoint, units=get_all_workers(), timeout=timeout, return_raw=return_raw
    )


def broadcast_get_across_workers_in_experiment(
    endpoint: str, experiment: str, timeout: float = 5.0, return_raw: bool = False
) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_get(
        endpoint=endpoint,
        units=get_all_workers_in_experiment(experiment),
        timeout=timeout,
        return_raw=return_raw,
    )


def broadcast_post_across_workers(
    endpoint: str,
    json: dict | None = None,
    params: dict | None = None,
    timeout: float = 30.0,
) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_post(endpoint, get_all_workers(), json=json, params=params, timeout=timeout)


def broadcast_delete_across_workers(endpoint: str, json: dict | None = None, timeout: float = 30.0) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_delete(endpoint, get_all_workers(), json=json, timeout=timeout)


def broadcast_patch_across_workers(endpoint: str, json: dict | None = None, timeout: float = 30.0) -> Result:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_patch(endpoint, get_all_workers(), json=json, timeout=timeout)


def _build_single_file_multipart(
    field_name: str, filename: str, content_type: str, payload: bytes
) -> tuple[str, bytes]:
    boundary = f"----PioreactorBoundary{uuid.uuid4().hex}"
    content_type = content_type or "application/octet-stream"
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        payload,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return boundary, b"".join(parts)


@api_bp.route("/models", methods=["GET"])
def get_models() -> ResponseReturnValue:
    """
    Return the list of supported Pioreactor models (name, version, display_name).
    """
    return attach_cache_control(jsonify({"models": list(get_registered_models().values())}))


@api_bp.route(
    "/workers/<pioreactor_unit>/jobs/stop/experiments/<experiment>",
    methods=["POST", "PATCH"],
)
def stop_all_jobs_on_worker_for_experiment(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    """Kills all jobs for worker assigned to experiment"""
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        broadcast_post_across_cluster("/unit_api/jobs/stop", json={"experiment": experiment})
    else:
        tasks.multicast_post("/unit_api/jobs/stop", [pioreactor_unit], json={"experiment": experiment})

    return {"status": "success"}, 202


@api_bp.route(
    "/workers/<pioreactor_unit>/jobs/stop/job_name/<job_name>/experiments/<experiment>",
    methods=["PATCH", "POST"],
)
@api_bp.route(
    "/units/<pioreactor_unit>/jobs/stop/job_name/<job_name>/experiments/<experiment>",
    methods=["PATCH", "POST"],
)
def stop_specific_job_on_unit(
    pioreactor_unit: str,
    job_name: str,
    experiment: str,
) -> ResponseReturnValue:
    """Kills specified job on unit"""

    msg = client.publish(
        f"pioreactor/{pioreactor_unit}/{experiment}/{job_name}/$state/set", b"disconnected", qos=1
    )
    try:
        msg.wait_for_publish(timeout=2.0)
    except Exception:
        # TODO: make this $broadcastable
        tasks.multicast_post("/unit_api/jobs/stop", [pioreactor_unit], json={"job_name": job_name})
        abort_with(500, "Failed to publish to mqtt")

    return {"status": "success"}, 202


@api_bp.route(
    "/units/<pioreactor_unit>/jobs/run/job_name/<job_name>/experiments/<experiment>",
    methods=["PATCH", "POST"],
)
@api_bp.route(
    "/workers/<pioreactor_unit>/jobs/run/job_name/<job_name>/experiments/<experiment>",
    methods=["PATCH", "POST"],
)
def run_job_on_unit_in_experiment(
    pioreactor_unit: str,
    job_name: str,
    experiment: str,
) -> DelayedResponseReturnValue:
    """
    Runs specified job on unit.

    The body is passed to the CLI, and should look like:

    {
      "options": {
        "option1": "value1",
        "option2": "value2"
      },
      "env": {},
      "args": ["arg1", "arg2"]
      "config_overrides": []

    }
    """
    json = current_app.get_json(request.data, type=structs.ArgsOptionsEnvsConfigOverrides)

    if experiment == UNIVERSAL_EXPERIMENT:
        # universal experiment, all workers
        if pioreactor_unit == UNIVERSAL_IDENTIFIER:
            assigned_workers = query_app_db(
                """
                SELECT pioreactor_unit, is_active, model_name, model_version
                FROM workers
                WHERE is_active = 1
                """
            )
            assert isinstance(assigned_workers, list)
        else:
            # universal experiment, specific worker
            worker = query_app_db(
                """
                SELECT pioreactor_unit, is_active, model_name, model_version
                FROM workers
                WHERE pioreactor_unit = ? AND is_active = 1
                """,
                (pioreactor_unit,),
                one=True,
            )
            if worker is None:
                assigned_workers = []
            else:
                assigned_workers = [worker]  # type: ignore
    else:
        if pioreactor_unit == UNIVERSAL_IDENTIFIER:
            # specific experiment, all workers
            assigned_workers = query_app_db(
                """
                SELECT a.pioreactor_unit, w.is_active, w.model_name, w.model_version
                FROM experiment_worker_assignments a
                JOIN workers w
                   on w.pioreactor_unit = a.pioreactor_unit
                WHERE experiment = ? and w.is_active = 1
                """,
                (experiment,),
            )
            assert isinstance(assigned_workers, list)
        else:
            # specific experiment, specific worker
            # check if worker is part of experiment
            worker = query_app_db(
                """
                SELECT a.pioreactor_unit, w.is_active, w.model_name, w.model_version
                FROM experiment_worker_assignments a
                JOIN workers w
                   on w.pioreactor_unit = a.pioreactor_unit
                WHERE a.experiment = ? AND w.pioreactor_unit = ? AND w.is_active = 1
                """,
                (experiment, pioreactor_unit),
                one=True,
            )
            if worker is None:
                assigned_workers = []
            else:
                assigned_workers = [worker]  # type: ignore

    if len(assigned_workers) == 0:
        if experiment == UNIVERSAL_EXPERIMENT:
            abort_with(404, f"Worker(s) {pioreactor_unit} not found or not active.")
        else:
            abort_with(
                404,
                f"Worker(s) {pioreactor_unit} not found, not active, or not assigned to experiment {experiment}.",
            )

    # Note we can include experiment in the env since we know these workers are in the experiment!

    t = tasks.multicast_post(
        f"/unit_api/jobs/run/job_name/{job_name}",
        [worker["pioreactor_unit"] for worker in assigned_workers],
        json=[
            {
                "args": json.args,
                "options": json.options,
                "config_overrides": json.config_overrides,
                "env": json.env
                | {
                    "EXPERIMENT": experiment,
                    "MODEL_NAME": worker["model_name"],
                    "MODEL_VERSION": worker["model_version"],
                    "HOSTNAME": worker["pioreactor_unit"],
                    "ACTIVE": str(int(worker["is_active"])),
                    "TESTING": str(int(is_testing_env())),
                    "DOT_PIOREACTOR": os.environ["DOT_PIOREACTOR"],
                },
            }
            for worker in assigned_workers
        ],
    )
    return create_task_response(t)


@api_bp.route("/units/<pioreactor_unit>/jobs/running", methods=["GET"])
@api_bp.route("/workers/<pioreactor_unit>/jobs/running", methods=["GET"])
def get_jobs_running(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        return create_task_response(broadcast_get_across_cluster("/unit_api/jobs/running"))
    else:
        return create_task_response(tasks.multicast_get("/unit_api/jobs/running", [pioreactor_unit]))


@api_bp.route("/workers/<pioreactor_unit>/blink", methods=["POST"])
def blink_worker(pioreactor_unit: str) -> ResponseReturnValue:
    msg = client.publish(
        f"pioreactor/{pioreactor_unit}/{UNIVERSAL_EXPERIMENT}/monitor/flicker_led_response_okay",
        1,
        qos=0,
    )
    msg.wait_for_publish(timeout=2.0)
    return {"status": "success"}, 202


@api_bp.route(
    "/workers/<pioreactor_unit>/jobs/update/job_name/<job_name>/experiments/<experiment>",
    methods=["PATCH"],
)
@api_bp.route(
    "/units/<pioreactor_unit>/jobs/update/job_name/<job_name>/experiments/<experiment>",
    methods=["PATCH"],
)
def update_job_on_unit(pioreactor_unit: str, job_name: str, experiment: str) -> ResponseReturnValue:
    """
    Update specified job on unit. Use $broadcast for everyone.

    The body should look like:

    {
      "settings": {
        <setting1>: <value1>,
        <setting2>: <value2>
      },
    }

    Example
    ----------

    ```
     curl -X PATCH "http://localhost:4999/api/workers/pio01/jobs/update/job_name/stirring/experiments/Exp001" \
     -H "Content-Type: application/json" \
     -d '{
           "settings": {
             "target_rpm": "200"
           }
         }'
    ```
    """
    try:
        for setting, value in request.get_json()["settings"].items():
            client.publish(
                f"pioreactor/{pioreactor_unit}/{experiment}/{job_name}/{setting}/set",
                value,
                qos=2,
            )
    except Exception as e:
        publish_to_error_log(str(e), "update_job_on_unit")
        abort_with(400, str(e))

    return {"status": "success"}, 202


@api_bp.route("/units/<pioreactor_unit>/system/reboot", methods=["POST"])
def reboot_unit(pioreactor_unit: str) -> DelayedResponseReturnValue:
    """Reboots unit"""
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_post_across_cluster("/unit_api/system/reboot")
    else:
        task = tasks.multicast_post("/unit_api/system/reboot", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/units/<pioreactor_unit>/system/shutdown", methods=["POST"])
def shutdown_unit(pioreactor_unit: str) -> DelayedResponseReturnValue:
    """Shutdown unit"""
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_post_across_cluster("/unit_api/system/shutdown")
    else:
        task = tasks.multicast_post("/unit_api/system/shutdown", [pioreactor_unit])
    return create_task_response(task)


## Clock


@api_bp.route("/units/<pioreactor_unit>/system/utc_clock", methods=["GET"])
def get_clocktime(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_cluster("/unit_api/system/utc_clock")
    else:
        task = tasks.multicast_get("/unit_api/system/utc_clock", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/system/utc_clock", methods=["POST"])
def set_clocktime() -> DelayedResponseReturnValue:
    # first update the leader:
    task1 = tasks.multicast_post(
        "/unit_api/system/utc_clock", [get_leader_hostname()], json=request.get_json()
    )
    task1.get(blocking=True, timeout=20)

    # then tell the workers to update to leader's value (via chrony)
    task2 = broadcast_post_across_cluster("/unit_api/system/utc_clock")
    return create_task_response(task2)


# util
def get_level_filter(min_level: str) -> tuple[str, tuple[str, ...]]:
    levels_by_threshold: dict[str, tuple[str, ...]] = {
        "DEBUG": ("ERROR", "WARNING", "NOTICE", "INFO", "DEBUG"),
        "INFO": ("ERROR", "WARNING", "NOTICE", "INFO"),
        "NOTICE": ("ERROR", "WARNING", "NOTICE"),
        "WARNING": ("ERROR", "WARNING"),
        "ERROR": ("ERROR",),
    }
    selected_levels = levels_by_threshold.get(min_level.upper(), levels_by_threshold["INFO"])
    placeholders = ", ".join("?" for _ in selected_levels)
    return f"level IN ({placeholders})", selected_levels


@api_bp.route("/experiments/<experiment>/recent_logs", methods=["GET"])
def get_recent_logs(experiment: str) -> ResponseReturnValue:
    """Shows recent event logs from all units"""

    min_level = request.args.get("min_level", "INFO")
    level_filter, level_params = get_level_filter(min_level)

    recent_logs = query_app_db(
        f"""SELECT l.timestamp, level, l.pioreactor_unit, message, task, l.experiment
            FROM logs AS l
            WHERE (l.experiment=? or l.experiment=?)
                AND {level_filter}
                AND l.timestamp >= MAX(
                    STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW', '-24 hours'),
                    COALESCE((SELECT created_at FROM experiments WHERE experiment=?), STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW', '-24 hours'))
                )
            ORDER BY l.timestamp DESC LIMIT 50;""",
        (UNIVERSAL_EXPERIMENT, experiment, *level_params, experiment),
    )

    return jsonify(recent_logs)


@api_bp.route("/logs", methods=["GET"])
def get_logs() -> ResponseReturnValue:
    """Shows event logs from all units, uses pagination."""

    skip = int(request.args.get("skip", 0))
    min_level = request.args.get("min_level", "INFO")
    level_filter, level_params = get_level_filter(min_level)

    recent_logs = query_app_db(
        f"""SELECT l.timestamp, level, l.pioreactor_unit, message, task, l.experiment
            FROM logs AS l
            WHERE {level_filter}
            ORDER BY l.timestamp DESC LIMIT 100 OFFSET ?;""",
        (*level_params, skip),
    )

    return jsonify(recent_logs)


@api_bp.route("/experiments/<experiment>/logs", methods=["GET"])
def get_exp_logs(experiment: str) -> ResponseReturnValue:
    """Shows event logs from all units, uses pagination."""

    skip = int(request.args.get("skip", 0))
    min_level = request.args.get("min_level", "INFO")
    level_filter, level_params = get_level_filter(min_level)

    recent_logs = query_app_db(
        f"""SELECT l.timestamp, l.level, l.pioreactor_unit, l.message, l.task, l.experiment
            FROM logs AS l
            WHERE (l.experiment=?)
            AND {level_filter}
            ORDER BY l.timestamp DESC LIMIT 100 OFFSET ?;""",
        (experiment, *level_params, skip),
    )

    return jsonify(recent_logs)


@api_bp.route("/workers/<pioreactor_unit>/experiments/<experiment>/recent_logs", methods=["GET"])
def get_recent_logs_for_unit_and_experiment(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    """Shows event logs for a specific unit within an experiment. This is for the single-page Pioreactor ui"""

    min_level = request.args.get("min_level", "INFO")
    level_filter, level_params = get_level_filter(min_level)

    recent_logs = query_app_db(
        f"""SELECT l.timestamp, level, l.pioreactor_unit, message, task, l.experiment
            FROM logs AS l
            WHERE (l.experiment=? OR l.experiment=?)
                AND (l.pioreactor_unit=? or l.pioreactor_unit=?)
                AND {level_filter}
                AND l.timestamp >= MAX(
                    STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW', '-24 hours'),
                    COALESCE((SELECT created_at FROM experiments WHERE experiment=?), STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW', '-24 hours'))
                )
            ORDER BY l.timestamp DESC LIMIT 50;""",
        (
            experiment,
            UNIVERSAL_EXPERIMENT,
            pioreactor_unit,
            UNIVERSAL_IDENTIFIER,
            *level_params,
            experiment,
        ),
    )

    return jsonify(recent_logs)


@api_bp.route("/workers/<pioreactor_unit>/experiments/<experiment>/logs", methods=["GET"])
def get_logs_for_unit_and_experiment(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    """Shows event logs from specific unit and experiment, uses pagination."""

    skip = int(request.args.get("skip", 0))
    min_level = request.args.get("min_level", "INFO")
    level_filter, level_params = get_level_filter(min_level)

    recent_logs = query_app_db(
        f"""SELECT l.timestamp, level, l.pioreactor_unit, message, task, l.experiment
            FROM logs AS l
            JOIN experiment_worker_assignments_history h
               on h.pioreactor_unit = l.pioreactor_unit
               and h.assigned_at <= l.timestamp
               and DATETIME(l.timestamp) <= DATETIME(coalesce(h.unassigned_at, STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')), '+5 seconds')
            WHERE (l.experiment=?)
                AND (l.pioreactor_unit=? or l.pioreactor_unit=?)
                AND {level_filter}
            ORDER BY l.timestamp DESC LIMIT 100 OFFSET ?;""",
        (experiment, pioreactor_unit, UNIVERSAL_IDENTIFIER, *level_params, skip),
    )

    return jsonify(recent_logs)


@api_bp.route("/units/<pioreactor_unit>/system_logs", methods=["GET"])
def get_system_logs_for_unit(pioreactor_unit: str) -> ResponseReturnValue:
    """Shows system logs from specific unit uses pagination."""

    skip = int(request.args.get("skip", 0))
    min_level = request.args.get("min_level", "INFO")
    level_filter, level_params = get_level_filter(min_level)

    recent_logs = query_app_db(
        f"""SELECT l.timestamp, l.level, l.pioreactor_unit, l.message, l.task, l.experiment
            FROM logs AS l
            WHERE (l.experiment=?)
                AND (l.pioreactor_unit=? or l.pioreactor_unit=?)
                AND {level_filter}
            ORDER BY l.timestamp DESC LIMIT 100 OFFSET ?;""",
        (UNIVERSAL_EXPERIMENT, pioreactor_unit, UNIVERSAL_IDENTIFIER, *level_params, skip),
    )

    return jsonify(recent_logs)


@api_bp.route("/units/<pioreactor_unit>/logs", methods=["GET"])
def get_logs_for_unit(pioreactor_unit: str) -> ResponseReturnValue:
    """Shows event logs from all units, uses pagination."""

    skip = int(request.args.get("skip", 0))
    min_level = request.args.get("min_level", "INFO")
    level_filter, level_params = get_level_filter(min_level)

    recent_logs = query_app_db(
        f"""SELECT l.timestamp, level, l.pioreactor_unit, message, task, l.experiment
            FROM logs AS l
            WHERE (l.pioreactor_unit=? or l.pioreactor_unit=?)
            AND {level_filter}
            ORDER BY l.timestamp DESC LIMIT 100 OFFSET ?;""",
        (pioreactor_unit, UNIVERSAL_IDENTIFIER, *level_params, skip),
    )

    return jsonify(recent_logs)


@api_bp.route("/workers/<pioreactor_unit>/experiments/<experiment>/logs", methods=["POST"])
@api_bp.route("/units/<pioreactor_unit>/experiments/<experiment>/logs", methods=["POST"])
def publish_new_log(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    body = request.get_json()
    source_ = body.get("source_", "ui")

    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        assigned_units = get_all_workers_in_experiment(experiment)
        for assigned_pioreactor_unit in assigned_units:
            topic = (
                f"pioreactor/{assigned_pioreactor_unit}/{experiment}/logs/{source_}/{body['level'].lower()}"
            )
            client.publish(
                topic,
                msg_to_JSON(
                    msg=body["message"],
                    source=body["source"],
                    level=body["level"].upper(),
                    timestamp=body["timestamp"],
                    task=body["task"] or "",
                ),
            )
    else:
        topic = f"pioreactor/{pioreactor_unit}/{experiment}/logs/{source_}/{body['level'].lower()}"
        client.publish(
            topic,
            msg_to_JSON(
                msg=body["message"],
                source=body["source"],
                level=body["level"].upper(),
                timestamp=body["timestamp"],
                task=body["task"] or "",
            ),
        )
    return {"status": "success"}, 202


## Time series data


@api_bp.route("/experiments/<experiment>/time_series/growth_rates", methods=["GET"])
def get_growth_rates(experiment: str) -> ResponseReturnValue:
    """Gets growth rates for all units"""
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    growth_rates = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   timestamp,
                   round(rate, 5) AS y
            FROM growth_rates INDEXED BY growth_rates_ix
            WHERE experiment=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT pioreactor_unit AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit
        );
        """,
        (experiment, cutoff_timestamp, target_points, target_points),
        one=True,
    )

    assert isinstance(growth_rates, dict)
    return attach_cache_control(as_json_response(growth_rates["json"]))


@api_bp.route("/experiments/<experiment>/time_series/temperature_readings", methods=["GET"])
def get_temperature_readings(experiment: str) -> ResponseReturnValue:
    """Gets temperature readings for all units"""
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    temperature_readings = query_app_db(
        """
        WITH numbered AS (
            SELECT unit,
                   timestamp,
                   y,
                   ROW_NUMBER() OVER (PARTITION BY unit ORDER BY timestamp) AS rn
            FROM (
                SELECT pioreactor_unit AS unit,
                       timestamp,
                       temperature_c AS y
                FROM temperature_readings
                WHERE experiment=? AND timestamp > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW' , ?)
            )
        ), steps AS (
            SELECT unit,
                   CASE WHEN ? > 0 THEN MAX(1, CAST((MAX(rn) + ? - 1) / ? AS INT)) ELSE 1 END AS step
            FROM numbered
            GROUP BY unit
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT numbered.unit,
                   json_group_array(json_object('x', timestamp, 'y', round(y, 2))) AS series_data
            FROM numbered
            JOIN steps USING (unit)
            WHERE (rn % step) = 0
            GROUP BY numbered.unit
        );
        """,
        (experiment, f"-{lookback} hours", target_points, target_points, target_points),
        one=True,
    )

    assert isinstance(temperature_readings, dict)
    return attach_cache_control(as_json_response(temperature_readings["json"]))


@api_bp.route("/experiments/<experiment>/time_series/od_readings_filtered", methods=["GET"])
def get_od_readings_filtered(experiment: str) -> ResponseReturnValue:
    """Gets normalized od for all units"""
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    filtered_od_readings = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   timestamp,
                   round(normalized_od_reading, 7) AS y
            FROM od_readings_filtered INDEXED BY od_readings_filtered_ix
            WHERE experiment=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT pioreactor_unit AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit
        );
        """,
        (experiment, cutoff_timestamp, target_points, target_points),
        one=True,
    )

    assert isinstance(filtered_od_readings, dict)
    return attach_cache_control(as_json_response(filtered_od_readings["json"]))


@api_bp.route("/experiments/<experiment>/time_series/od_readings", methods=["GET"])
def get_od_readings(experiment: str) -> ResponseReturnValue:
    """Gets raw od for all units"""
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    raw_od_readings = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   channel,
                   timestamp,
                   round(od_reading, 7) AS y
            FROM od_readings
            WHERE experiment=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   channel,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit, channel
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT (pioreactor_unit || '-' || channel) AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit, channel)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit, channel
        );
        """,
        (experiment, cutoff_timestamp, target_points, target_points),
        one=True,
    )

    assert isinstance(raw_od_readings, dict)
    return attach_cache_control(as_json_response(raw_od_readings["json"]))


@api_bp.route("/experiments/<experiment>/time_series/od_readings_fused", methods=["GET"])
def get_od_readings_fused(experiment: str) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    fused_od_readings = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   timestamp,
                   round(od_reading, 7) AS y
            FROM od_readings_fused
            WHERE experiment=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT pioreactor_unit AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit
        );
        """,
        (experiment, cutoff_timestamp, target_points, target_points),
        one=True,
    )

    assert isinstance(fused_od_readings, dict)
    return attach_cache_control(as_json_response(fused_od_readings["json"]))


@api_bp.route("/experiments/<experiment>/time_series/raw_od_readings", methods=["GET"])
def get_od_raw_readings(experiment: str) -> ResponseReturnValue:
    """Gets raw od for all units"""
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    raw_od_readings = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   channel,
                   timestamp,
                   round(od_reading, 7) AS y
            FROM raw_od_readings INDEXED BY raw_od_readings_ix
            WHERE experiment=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   channel,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit, channel
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT (pioreactor_unit || '-' || channel) AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit, channel)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit, channel
        );
        """,
        (experiment, cutoff_timestamp, target_points, target_points),
        one=True,
    )

    assert isinstance(raw_od_readings, dict)
    return attach_cache_control(as_json_response(raw_od_readings["json"]))


@api_bp.route("/experiments/<experiment>/time_series/<data_source>/<column>", methods=["GET"])
def get_fallback_time_series(experiment: str, data_source: str, column: str) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    try:
        data_source = scrub_to_valid(data_source)
        column = scrub_to_valid(column)
        r = query_app_db(
            f"""
                WITH numbered AS (
                    SELECT unit,
                           timestamp,
                           y,
                           ROW_NUMBER() OVER (PARTITION BY unit ORDER BY timestamp) AS rn
                    FROM (
                        SELECT pioreactor_unit AS unit,
                               timestamp,
                               {column} AS y
                        FROM {data_source}
                        WHERE experiment=? AND timestamp > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW',?) AND {column} IS NOT NULL
                    )
                ), steps AS (
                    SELECT unit,
                           CASE WHEN ? > 0 THEN MAX(1, CAST((MAX(rn) + ? - 1) / ? AS INT)) ELSE 1 END AS step
                    FROM numbered
                    GROUP BY unit
                )
                SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
                FROM (
                    SELECT numbered.unit,
                           json_group_array(json_object('x', timestamp, 'y', round(y, 7))) AS series_data
                    FROM numbered
                    JOIN steps USING (unit)
                    WHERE (rn % step) = 0
                    GROUP BY numbered.unit
                );
                """,
            (experiment, f"-{lookback} hours", target_points, target_points, target_points),
            one=True,
        )

    except Exception as e:
        publish_to_error_log(str(e), "get_fallback_time_series")
        abort_with(400, str(e))

    assert isinstance(r, dict)
    return attach_cache_control(as_json_response(r["json"]))


@api_bp.route("/workers/<pioreactor_unit>/experiments/<experiment>/time_series/growth_rates", methods=["GET"])
def get_growth_rates_per_unit(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    growth_rates = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   timestamp,
                   round(rate, 5) AS y
            FROM growth_rates INDEXED BY growth_rates_ix
            WHERE experiment=? AND pioreactor_unit=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT pioreactor_unit AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit
        );
        """,
        (
            experiment,
            pioreactor_unit,
            cutoff_timestamp,
            target_points,
            target_points,
        ),
        one=True,
    )

    assert isinstance(growth_rates, dict)
    return attach_cache_control(as_json_response(growth_rates["json"]))


@api_bp.route(
    "/workers/<pioreactor_unit>/experiments/<experiment>/time_series/temperature_readings",
    methods=["GET"],
)
def get_temperature_readings_per_unit(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    temperature_readings = query_app_db(
        """
        WITH numbered AS (
            SELECT unit,
                   timestamp,
                   y,
                   ROW_NUMBER() OVER (PARTITION BY unit ORDER BY timestamp) AS rn
            FROM (
                SELECT pioreactor_unit AS unit,
                       timestamp,
                       temperature_c AS y
                FROM temperature_readings
                WHERE experiment=? AND pioreactor_unit=? AND timestamp > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW' , ?)
            )
        ), steps AS (
            SELECT unit,
                   CASE WHEN ? > 0 THEN MAX(1, CAST((MAX(rn) + ? - 1) / ? AS INT)) ELSE 1 END AS step
            FROM numbered
            GROUP BY unit
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT numbered.unit,
                   json_group_array(json_object('x', timestamp, 'y', round(y, 2))) AS series_data
            FROM numbered
            JOIN steps USING (unit)
            WHERE (rn % step) = 0
            GROUP BY numbered.unit
        );
        """,
        (experiment, pioreactor_unit, f"-{lookback} hours", target_points, target_points, target_points),
        one=True,
    )

    assert isinstance(temperature_readings, dict)
    return attach_cache_control(as_json_response(temperature_readings["json"]))


@api_bp.route(
    "/workers/<pioreactor_unit>/experiments/<experiment>/time_series/od_readings_filtered",
    methods=["GET"],
)
def get_od_readings_filtered_per_unit(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    filtered_od_readings = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   timestamp,
                   round(normalized_od_reading, 7) AS y
            FROM od_readings_filtered INDEXED BY od_readings_filtered_ix
            WHERE experiment=? AND pioreactor_unit=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT pioreactor_unit AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit
        );
        """,
        (
            experiment,
            pioreactor_unit,
            cutoff_timestamp,
            target_points,
            target_points,
        ),
        one=True,
    )

    assert isinstance(filtered_od_readings, dict)
    return attach_cache_control(as_json_response(filtered_od_readings["json"]))


@api_bp.route("/workers/<pioreactor_unit>/experiments/<experiment>/time_series/od_readings", methods=["GET"])
def get_od_readings_per_unit(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    raw_od_readings = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   channel,
                   timestamp,
                   round(od_reading, 7) AS y
            FROM od_readings
            WHERE experiment=? AND pioreactor_unit=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   channel,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit, channel
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT (pioreactor_unit || '-' || channel) AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit, channel)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit, channel
        );
        """,
        (experiment, pioreactor_unit, cutoff_timestamp, target_points, target_points),
        one=True,
    )

    assert isinstance(raw_od_readings, dict)
    return attach_cache_control(as_json_response(raw_od_readings["json"]))


@api_bp.route(
    "/workers/<pioreactor_unit>/experiments/<experiment>/time_series/od_readings_fused",
    methods=["GET"],
)
def get_od_readings_fused_per_unit(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    fused_od_readings = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   timestamp,
                   round(od_reading, 7) AS y
            FROM od_readings_fused
            WHERE experiment=? AND pioreactor_unit=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT pioreactor_unit AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit
        );
        """,
        (
            experiment,
            pioreactor_unit,
            cutoff_timestamp,
            target_points,
            target_points,
        ),
        one=True,
    )

    assert isinstance(fused_od_readings, dict)
    return attach_cache_control(as_json_response(fused_od_readings["json"]))


@api_bp.route(
    "/workers/<pioreactor_unit>/experiments/<experiment>/time_series/raw_od_readings",
    methods=["GET"],
)
def get_od_raw_readings_per_unit(pioreactor_unit: str, experiment: str) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    cutoff_timestamp = format_utc_timestamp_for_lookback_hours(lookback)

    raw_od_readings = query_app_db(
        """
        WITH filtered AS (
            SELECT pioreactor_unit,
                   channel,
                   timestamp,
                   round(od_reading, 7) AS y
            FROM raw_od_readings INDEXED BY raw_od_readings_ix
            WHERE experiment=? AND pioreactor_unit=? AND timestamp > ?
        ), stats AS (
            SELECT pioreactor_unit,
                   channel,
                   COUNT(*) AS total
            FROM filtered
            GROUP BY pioreactor_unit, channel
        )
        SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
        FROM (
            SELECT (pioreactor_unit || '-' || channel) AS unit,
                   json_group_array(json_object('x', timestamp, 'y', y)) AS series_data
            FROM filtered
            JOIN stats USING (pioreactor_unit, channel)
            WHERE total <= ? OR (abs(random()) % total) < ?
            GROUP BY pioreactor_unit, channel
        );
        """,
        (experiment, pioreactor_unit, cutoff_timestamp, target_points, target_points),
        one=True,
    )

    assert isinstance(raw_od_readings, dict)
    return attach_cache_control(as_json_response(raw_od_readings["json"]))


@api_bp.route(
    "/workers/<pioreactor_unit>/experiments/<experiment>/time_series/<data_source>/<column>",
    methods=["GET"],
)
def get_fallback_time_series_per_unit(
    pioreactor_unit: str, experiment: str, data_source: str, column: str
) -> ResponseReturnValue:
    args = request.args
    lookback = float(args.get("lookback", 4.0))
    target_points = int(args.get("target_points", 720))
    if not target_points or target_points <= 0:
        abort_with(400, "target_points must be > 0")

    try:
        data_source = scrub_to_valid(data_source)
        column = scrub_to_valid(column)
        r = query_app_db(
            f"""
                WITH numbered AS (
                    SELECT unit,
                           timestamp,
                           y,
                           ROW_NUMBER() OVER (PARTITION BY unit ORDER BY timestamp) AS rn
                    FROM (
                        SELECT pioreactor_unit AS unit,
                               timestamp,
                               {column} AS y
                        FROM {data_source}
                        WHERE experiment=? AND timestamp > STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW',?) AND pioreactor_unit=? AND {column} IS NOT NULL
                    )
                ), steps AS (
                    SELECT unit,
                           CASE WHEN ? > 0 THEN MAX(1, CAST((MAX(rn) + ? - 1) / ? AS INT)) ELSE 1 END AS step
                    FROM numbered
                    GROUP BY unit
                )
                SELECT json_object('series', json_group_array(unit), 'data', json_group_array(json(series_data))) AS json
                FROM (
                    SELECT numbered.unit,
                           json_group_array(json_object('x', timestamp, 'y', round(y, 7))) AS series_data
                    FROM numbered
                    JOIN steps USING (unit)
                    WHERE (rn % step) = 0
                    GROUP BY numbered.unit
                );
                """,
            (experiment, f"-{lookback} hours", pioreactor_unit, target_points, target_points, target_points),
            one=True,
        )

    except Exception as e:
        publish_to_error_log(str(e), "get_fallback_time_series")
        abort_with(400, str(e))

    assert isinstance(r, dict)
    return attach_cache_control(as_json_response(r["json"]))


@api_bp.route("/experiments/<experiment>/media_rates", methods=["GET"])
def get_media_rates(experiment: str) -> ResponseReturnValue:
    """
    Shows amount of added media per unit. Note that it only consider values from a dosing automation (i.e. not manual dosing, which includes continously dose)

    """
    ## this one confusing

    try:
        rows = query_app_db(
            """
            SELECT
                d.pioreactor_unit,
                SUM(CASE WHEN event='add_media' THEN volume_change_ml ELSE 0 END) / 3 AS mediaRate,
                SUM(CASE WHEN event='add_alt_media' THEN volume_change_ml ELSE 0 END) / 3 AS altMediaRate
            FROM dosing_events AS d
            WHERE
                datetime(d.timestamp) >= datetime('now', '-3 hours') AND
                event IN ('add_alt_media', 'add_media') AND
                experiment = ?
            GROUP BY d.pioreactor_unit;
            """,
            (experiment,),
        )
        assert isinstance(rows, list)
        json_result: dict[str, dict[str, float]] = {}
        aggregate: dict[str, float] = {"altMediaRate": 0.0, "mediaRate": 0.0}

        for row in rows:
            json_result[row["pioreactor_unit"]] = {
                "altMediaRate": float(row["altMediaRate"]),
                "mediaRate": float(row["mediaRate"]),
            }
            aggregate["mediaRate"] = aggregate["mediaRate"] + float(row["mediaRate"])
            aggregate["altMediaRate"] = aggregate["altMediaRate"] + float(row["altMediaRate"])

        json_result["all"] = aggregate
        return attach_cache_control(jsonify(json_result))

    except Exception as e:
        publish_to_error_log(str(e), "get_media_rates")
        abort_with(500, str(e))


## CALIBRATIONS


@api_bp.route("/workers/<pioreactor_unit>/calibration_protocols", methods=["GET"])
def get_calibration_protocols(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers("/unit_api/calibration_protocols")
    else:
        task = tasks.multicast_get("/unit_api/calibration_protocols", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/calibrations", methods=["GET"])
def get_all_calibrations(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers("/unit_api/calibrations")
    else:
        task = tasks.multicast_get("/unit_api/calibrations", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/active_calibrations", methods=["GET"])
def get_all_active_calibrations(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers("/unit_api/active_calibrations")
    else:
        task = tasks.multicast_get("/unit_api/active_calibrations", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/active_estimators", methods=["GET"])
def get_all_active_estimators(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers("/unit_api/active_estimators")
    else:
        task = tasks.multicast_get("/unit_api/active_estimators", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/estimators", methods=["GET"])
def get_all_estimators(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers("/unit_api/estimators")
    else:
        task = tasks.multicast_get("/unit_api/estimators", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/zipped_calibrations", methods=["GET"])
def get_all_calibrations_as_yamls(pioreactor_unit: str) -> ResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers("/unit_api/zipped_calibrations", return_raw=True)
    else:
        task = tasks.multicast_get("/unit_api/zipped_calibrations", [pioreactor_unit], return_raw=True)

    try:
        results = task.get(blocking=True, timeout=60)
    except (HueyException, TaskException):
        abort_with(
            500,
            "Timed out fetching calibrations",
            cause="Timed out waiting for workers to provide calibration archives.",
            remediation="Retry the request and check worker connectivity.",
        )

    aggregate_buffer = BytesIO()

    with zipfile.ZipFile(aggregate_buffer, "w", zipfile.ZIP_DEFLATED) as aggregate_zip:
        for worker, content in results.items():
            if content is None:
                continue  # worker did not respond
            # Load the remote ZIP into memory
            remote_zip_buffer = BytesIO(content)
            with zipfile.ZipFile(remote_zip_buffer, "r") as remote_zip:
                # Iterate over each file in the remote ZIP
                for file_info in remote_zip.infolist():
                    # Read file contents
                    with remote_zip.open(file_info) as file_data:
                        contents = file_data.read()

                    # Build a prefixed path to avoid collisions
                    new_name = f"{worker}/{file_info.filename}"

                    # Add the file to our aggregator zip
                    aggregate_zip.writestr(new_name, contents)

    # Reset the buffer's position
    aggregate_buffer.seek(0)

    # Send the aggregated ZIP as a downloadable file
    return send_file(
        aggregate_buffer,
        as_attachment=True,
        download_name="calibration_yamls.zip",
        mimetype="application/zip",
    )


@api_bp.route("/units/<pioreactor_unit>/zipped_dot_pioreactor", methods=["GET"])
def get_entire_dot_pioreactor(pioreactor_unit: str) -> ResponseReturnValue:
    """Download a ZIP of ~/.pioreactor from one or all workers.

    - For a specific worker, fetch raw bytes from its unit_api and proxy as a download.
    - For "$broadcast", gather from all workers and aggregate into a single ZIP
      with each worker's files under a prefix of its hostname.
    """
    endpoint = "/unit_api/zipped_dot_pioreactor"
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_cluster(endpoint, return_raw=True, timeout=60)
    else:
        task = tasks.multicast_get(endpoint, [pioreactor_unit], return_raw=True, timeout=60)

    try:
        results = task.get(blocking=True, timeout=120)
    except (HueyException, TaskException):
        abort_with(
            500,
            "Timed out fetching .pioreactor archive",
            cause="Timed out waiting for worker responses.",
            remediation="Retry the request and check worker connectivity.",
        )

    # If only one worker, proxy its ZIP directly
    if isinstance(results, dict) and len(results) == 1:
        content = next(iter(results.values()))
        if content is None:
            abort_with(
                502,
                "No data received from worker",
                cause="Worker returned an empty response body.",
                remediation="Check worker connectivity and retry.",
            )
        buf = BytesIO(content)
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name="dot_pioreactor.zip",
            mimetype="application/zip",
        )

    # Aggregate multiple zips into a single zip
    aggregate_buffer = BytesIO()
    with zipfile.ZipFile(aggregate_buffer, "w", zipfile.ZIP_DEFLATED) as aggregate_zip:
        for worker, content in (results or {}).items():
            if content is None:
                continue
            remote_zip_buffer = BytesIO(content)
            with zipfile.ZipFile(remote_zip_buffer, "r") as remote_zip:
                for file_info in remote_zip.infolist():
                    with remote_zip.open(file_info) as file_data:
                        contents = file_data.read()
                    new_name = f"{worker}/{file_info.filename}"
                    aggregate_zip.writestr(new_name, contents)

    aggregate_buffer.seek(0)
    return send_file(
        aggregate_buffer,
        as_attachment=True,
        download_name="cluster_dot_pioreactor.zip",
        mimetype="application/zip",
    )


@api_bp.route("/units/<pioreactor_unit>/import_zipped_dot_pioreactor", methods=["POST"])
def import_dot_pioreactor_archive(pioreactor_unit: str) -> ResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        abort_with(
            400,
            "Cannot import to $broadcast; choose a specific Pioreactor.",
            cause="Import requires a single target unit.",
            remediation="Specify a concrete pioreactor_unit in the URL.",
        )

    uploaded = request.files.get("archive")
    if uploaded is None or uploaded.filename == "":
        abort_with(
            400,
            "No archive uploaded",
            cause="Missing 'archive' file in multipart form-data.",
            remediation="Upload a zip file using the 'archive' field.",
        )

    try:
        filename = secure_filename(uploaded.filename) or "archive.zip"
        temp_basename = f"import_dot_pioreactor_{uuid.uuid4().hex}_{filename}"
        temp_path = Path(safe_join(tempfile.gettempdir(), temp_basename))
        uploaded.save(temp_path)
    except Exception as exc:
        publish_to_error_log(str(exc), "import_zipped_dot_pioreactor")
        abort_with(
            500,
            "Failed to save uploaded archive",
            cause="Unable to write uploaded file to temporary storage.",
            remediation="Check disk space and file permissions, then retry.",
        )

    payload = temp_path.read_bytes()
    temp_path.unlink(missing_ok=True)

    boundary, body = _build_single_file_multipart(
        field_name="archive",
        filename=filename,
        content_type="application/zip",
        payload=payload,
    )

    try:
        response = post_into(
            resolve_to_address(pioreactor_unit),
            "/unit_api/import_zipped_dot_pioreactor",
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            timeout=120,
        )
        response.raise_for_status()
    except (HTTPErrorStatus, HTTPException) as exc:
        publish_to_error_log(str(exc), "import_zipped_dot_pioreactor")
        abort_with(
            502,
            f"Importing system files failed on {pioreactor_unit}. See system logs.",
            cause="Worker returned an error during import.",
            remediation="Check worker logs and retry the import.",
        )

    return Response(
        response.content,
        status=response.status_code,
        content_type=response.headers.get("Content-Type", "application/json"),
    )


@api_bp.route("/workers/<pioreactor_unit>/calibrations/<device>", methods=["GET"])
def get_calibrations(pioreactor_unit: str, device: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers(f"/unit_api/calibrations/{device}")
    else:
        task = tasks.multicast_get(f"/unit_api/calibrations/{device}", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/calibrations/<device>/<cal_name>", methods=["GET"])
def get_calibration(pioreactor_unit: str, device: str, cal_name: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers(f"/unit_api/calibrations/{device}/{cal_name}")
    else:
        task = tasks.multicast_get(f"/unit_api/calibrations/{device}/{cal_name}", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/estimators/<device>", methods=["GET"])
def get_estimators_by_device(pioreactor_unit: str, device: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers(f"/unit_api/estimators/{device}")
    else:
        task = tasks.multicast_get(f"/unit_api/estimators/{device}", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/estimators/<device>/<estimator_name>", methods=["GET"])
def get_estimator(pioreactor_unit: str, device: str, estimator_name: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers(f"/unit_api/estimators/{device}/{estimator_name}")
    else:
        task = tasks.multicast_get(f"/unit_api/estimators/{device}/{estimator_name}", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/calibrations/<device>", methods=["POST"])
def create_calibration(pioreactor_unit: str, device: str) -> DelayedResponseReturnValue:
    yaml_data = request.get_json()["calibration_data"]

    if not yaml_data:
        abort_with(
            400,
            "YAML data is missing.",
            cause="Request JSON missing calibration_data.",
            remediation="Provide calibration_data with a valid YAML payload.",
        )

    try:
        yaml_decode(yaml_data, type=AllCalibrations)
    except Exception as e:
        publish_to_error_log(str(e), "create_calibration")
        abort_with(
            400,
            description=f"YAML data is not correct, or required calibration struct missing: {str(e)}",
            cause="Calibration YAML failed schema validation.",
            remediation="Fix the YAML structure and retry.",
        )

    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_post_across_workers(f"/unit_api/calibrations/{device}", request.get_json())
    else:
        task = tasks.multicast_post(f"/unit_api/calibrations/{device}", [pioreactor_unit], request.get_json())
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/calibrations/sessions", methods=["POST"])
def start_calibration_session(pioreactor_unit: str) -> ResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        abort_with(
            400,
            "Cannot start sessions with $broadcast; choose a specific Pioreactor.",
            cause="Calibration sessions require a single target unit.",
            remediation="Specify a concrete pioreactor_unit in the URL.",
        )

    body = request.get_json()
    if body is None:
        abort_with(
            400,
            description="Missing JSON payload.",
            cause="Request body is empty or not JSON.",
            remediation="Send a JSON payload describing the calibration session.",
        )

    response: Response | None = None
    try:
        response = post_into(
            resolve_to_address(pioreactor_unit),
            "/unit_api/calibrations/sessions",
            json=body,
            timeout=30,
        )
        response.raise_for_status()
    except (HTTPErrorStatus, HTTPException):
        detail = _extract_unit_api_error(response)
        if detail:
            abort_with(502, f"{detail}")
        if response is not None:
            abort_with(
                502,
                f"Starting calibration session failed on {pioreactor_unit} (HTTP {response.status_code}).",
            )
        abort_with(502, f"Starting calibration session failed on {pioreactor_unit}.")

    return Response(
        response.content,
        status=response.status_code,
        content_type=response.headers.get("Content-Type", "application/json"),
    )


@api_bp.route("/workers/<pioreactor_unit>/calibrations/sessions/<session_id>", methods=["GET"])
def get_calibration_session(pioreactor_unit: str, session_id: str) -> ResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        abort_with(
            400,
            "Cannot fetch sessions with $broadcast; choose a specific Pioreactor.",
            cause="Calibration sessions require a single target unit.",
            remediation="Specify a concrete pioreactor_unit in the URL.",
        )

    response: Response | None = None
    try:
        response = get_from(
            resolve_to_address(pioreactor_unit),
            f"/unit_api/calibrations/sessions/{session_id}",
            timeout=30,
        )
        response.raise_for_status()
    except (HTTPErrorStatus, HTTPException):
        detail = _extract_unit_api_error(response)
        if detail:
            abort_with(502, f"Fetching calibration session failed on {pioreactor_unit}: {detail}")
        if response is not None:
            abort_with(
                502,
                f"Fetching calibration session failed on {pioreactor_unit} (HTTP {response.status_code}).",
            )
        abort_with(502, f"Fetching calibration session failed on {pioreactor_unit}.")

    return Response(
        response.content,
        status=response.status_code,
        content_type=response.headers.get("Content-Type", "application/json"),
    )


@api_bp.route("/workers/<pioreactor_unit>/calibrations/sessions/<session_id>/inputs", methods=["POST"])
def advance_calibration_session(pioreactor_unit: str, session_id: str) -> ResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        abort_with(
            400,
            "Cannot update sessions with $broadcast; choose a specific Pioreactor.",
            cause="Calibration sessions require a single target unit.",
            remediation="Specify a concrete pioreactor_unit in the URL.",
        )

    body = request.get_json()
    if body is None:
        abort_with(
            400,
            description="Missing JSON payload.",
            cause="Request body is empty or not JSON.",
            remediation="Send a JSON payload with calibration inputs.",
        )

    response: Response | None = None
    try:
        response = post_into(
            resolve_to_address(pioreactor_unit),
            f"/unit_api/calibrations/sessions/{session_id}/inputs",
            json=body,
            timeout=300,
        )
        response.raise_for_status()
    except (HTTPErrorStatus, HTTPException):
        detail = _extract_unit_api_error(response)
        if detail:
            abort_with(502, detail)
        if response is not None:
            abort_with(
                502,
                f"Updating calibration session failed on {pioreactor_unit} (HTTP {response.status_code}).",
            )
        abort_with(502, f"Updating calibration session failed on {pioreactor_unit}.")

    return Response(
        response.content,
        status=response.status_code,
        content_type=response.headers.get("Content-Type", "application/json"),
    )


@api_bp.route("/workers/<pioreactor_unit>/calibrations/sessions/<session_id>/abort", methods=["POST"])
def abort_calibration_session(pioreactor_unit: str, session_id: str) -> ResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        abort_with(
            400,
            "Cannot abort sessions with $broadcast; choose a specific Pioreactor.",
            cause="Calibration sessions require a single target unit.",
            remediation="Specify a concrete pioreactor_unit in the URL.",
        )

    response: Response | None = None
    try:
        response = post_into(
            resolve_to_address(pioreactor_unit),
            f"/unit_api/calibrations/sessions/{session_id}/abort",
            timeout=30,
        )
        response.raise_for_status()
    except (HTTPErrorStatus, HTTPException):
        detail = _extract_unit_api_error(response)
        if detail:
            abort_with(502, f"Aborting calibration session failed on {pioreactor_unit}: {detail}")
        if response is not None:
            abort_with(
                502,
                f"Aborting calibration session failed on {pioreactor_unit} (HTTP {response.status_code}).",
            )
        abort_with(502, f"Aborting calibration session failed on {pioreactor_unit}.")

    return Response(
        response.content,
        status=response.status_code,
        content_type=response.headers.get("Content-Type", "application/json"),
    )


@api_bp.route("/workers/<pioreactor_unit>/active_calibrations/<device>/<cal_name>", methods=["PATCH"])
def set_active_calibration(pioreactor_unit, device, cal_name) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_patch_across_workers(f"/unit_api/active_calibrations/{device}/{cal_name}")
    else:
        task = tasks.multicast_patch(f"/unit_api/active_calibrations/{device}/{cal_name}", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/active_estimators/<device>/<estimator_name>", methods=["PATCH"])
def set_active_estimator(pioreactor_unit, device, estimator_name) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_patch_across_workers(f"/unit_api/active_estimators/{device}/{estimator_name}")
    else:
        task = tasks.multicast_patch(
            f"/unit_api/active_estimators/{device}/{estimator_name}", [pioreactor_unit]
        )
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/active_calibrations/<device>", methods=["DELETE"])
def remove_active_status_calibration(pioreactor_unit, device) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_delete_across_workers(f"/unit_api/active_calibrations/{device}")
    else:
        task = tasks.multicast_delete(f"/unit_api/active_calibrations/{device}", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/active_estimators/<device>", methods=["DELETE"])
def remove_active_status_estimator(pioreactor_unit, device) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_delete_across_workers(f"/unit_api/active_estimators/{device}")
    else:
        task = tasks.multicast_delete(f"/unit_api/active_estimators/{device}", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/calibrations/<device>/<cal_name>", methods=["DELETE"])
def delete_calibration(pioreactor_unit, device, cal_name) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_delete_across_workers(f"/unit_api/calibrations/{device}/{cal_name}")
    else:
        task = tasks.multicast_delete(f"/unit_api/calibrations/{device}/{cal_name}", [pioreactor_unit])
    return create_task_response(task)


@api_bp.route("/workers/<pioreactor_unit>/estimators/<device>/<estimator_name>", methods=["DELETE"])
def delete_estimator(pioreactor_unit, device, estimator_name) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_delete_across_workers(f"/unit_api/estimators/{device}/{estimator_name}")
    else:
        task = tasks.multicast_delete(f"/unit_api/estimators/{device}/{estimator_name}", [pioreactor_unit])
    return create_task_response(task)


## PLUGINS


@api_bp.route("/units/<pioreactor_unit>/plugins/installed", methods=["GET"])
def get_plugins_on_machine(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_cluster("/unit_api/plugins/installed", timeout=5)
    else:
        task = tasks.multicast_get("/unit_api/plugins/installed", [pioreactor_unit], timeout=5)

    return create_task_response(task)


@api_bp.route("/units/<pioreactor_unit>/plugins/install", methods=["POST", "PATCH"])
def install_plugin_across_cluster(pioreactor_unit: str) -> DelayedResponseReturnValue:
    # there is a security problem here. See https://github.com/Pioreactor/pioreactor/issues/421
    if (Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_INSTALLS").is_file():
        abort_with(403, "Not UI installed allowed.")

    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        return create_task_response(
            broadcast_post_across_cluster("/unit_api/plugins/install", request.get_json())
        )
    else:
        return create_task_response(
            tasks.multicast_post("/unit_api/plugins/install", [pioreactor_unit], request.get_json())
        )


@api_bp.route("/units/<pioreactor_unit>/plugins/uninstall", methods=["POST", "PATCH"])
def uninstall_plugin_across_cluster(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if (Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_INSTALLS").is_file():
        abort_with(403, "No UI uninstall allowed")

    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        return create_task_response(
            broadcast_post_across_cluster("/unit_api/plugins/uninstall", request.get_json())
        )
    else:
        return create_task_response(
            tasks.multicast_post("/unit_api/plugins/uninstall", [pioreactor_unit], request.get_json())
        )


@api_bp.route("/units/<pioreactor_unit>/capabilities", methods=["GET"])
@api_bp.route("/workers/<pioreactor_unit>/capabilities", methods=["GET"])
def get_capabilities(pioreactor_unit: str) -> ResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        return create_task_response(broadcast_get_across_cluster("/unit_api/capabilities", timeout=15))
    else:
        return create_task_response(
            tasks.multicast_get("/unit_api/capabilities", [pioreactor_unit], timeout=15)
        )


### SETTINGS


@api_bp.route(
    "/workers/<pioreactor_unit>/jobs/settings/job_name/<job_name>/experiments/<experiment>", methods=["GET"]
)
def get_job_settings_for_worker(
    pioreactor_unit: str,
    job_name: str,
    experiment: str,
) -> DelayedResponseReturnValue:
    endpoint = f"/unit_api/jobs/settings/job_name/{job_name}"
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers_in_experiment(endpoint, experiment)
    else:
        workers = get_all_workers_in_experiment(experiment)
        if pioreactor_unit not in workers:
            abort_with(404, f"{pioreactor_unit} not in experiment {experiment}")
        task = tasks.multicast_get(endpoint, [pioreactor_unit])

    return create_task_response(task)


@api_bp.route(
    "/workers/<pioreactor_unit>/jobs/settings/job_name/<job_name>/setting/<setting>/experiments/<experiment>",
    methods=["GET"],
)
def get_job_setting_for_worker(
    pioreactor_unit: str,
    job_name: str,
    setting: str,
    experiment: str,
) -> DelayedResponseReturnValue:
    endpoint = f"/unit_api/jobs/settings/job_name/{job_name}/setting/{setting}"
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        task = broadcast_get_across_workers_in_experiment(endpoint, experiment)
    else:
        workers = get_all_workers_in_experiment(experiment)
        if pioreactor_unit not in workers:
            abort_with(404, f"{pioreactor_unit} not in experiment {experiment}")
        task = tasks.multicast_get(endpoint, [pioreactor_unit])

    return create_task_response(task)


## MISC


@api_bp.route("/units/<pioreactor_unit>/versions/app", methods=["GET"])
def get_app_versions(pioreactor_unit: str) -> DelayedResponseReturnValue:
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        return create_task_response(broadcast_get_across_cluster("/unit_api/versions/app"))
    else:
        return create_task_response(tasks.multicast_get("/unit_api/versions/app", [pioreactor_unit]))


@api_bp.route("/system/upload", methods=["POST"])
def upload() -> ResponseReturnValue:
    if (Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_UPLOADS").is_file():
        abort_with(403, "No UI uploads allowed")

    if "file" not in request.files:
        abort_with(
            400,
            "No file part",
            cause="Request missing multipart form-data field 'file'.",
            remediation="Send a multipart form-data request with a 'file' field.",
        )

    file = request.files["file"]

    # If the user does not select a file, the browser submits an
    # empty file without a filename.
    if file.filename == "":
        abort_with(
            400,
            "No selected file",
            cause="Uploaded file field has an empty filename.",
            remediation="Select a file before submitting the form.",
        )
    if file.content_length >= 30_000_000:  # 30mb?
        abort_with(
            400,
            "Too large",
            cause="Uploaded file exceeds 30 MB limit.",
            remediation="Upload a smaller file (under 30 MB).",
        )

    filename = secure_filename(file.filename)
    save_path = safe_join(tempfile.gettempdir(), filename)
    file.save(save_path)
    return jsonify({"message": "File successfully uploaded", "save_path": save_path}), 200


@api_bp.route("/contrib/automations/<automation_type>", methods=["GET"])
def get_automation_contrib(automation_type: str) -> ResponseReturnValue:
    # security to prevent possibly reading arbitrary file
    if automation_type not in {"temperature", "dosing", "led"}:
        abort_with(
            400, "Not a valid automation type", remediation="choose one of 'temperature', 'dosing', 'led'"
        )

    try:
        automation_path_plugins = (
            Path(os.environ["DOT_PIOREACTOR"]) / "plugins" / "ui" / "automations" / automation_type
        )
        automation_path_builtins = Path(os.environ["DOT_PIOREACTOR"]) / "ui" / "automations" / automation_type
        files = sorted(automation_path_builtins.glob("*.y*ml")) + sorted(
            automation_path_plugins.glob("*.y*ml")
        )

        # we dedup based on 'automation_name'.
        parsed_yaml = {}
        for file in files:
            try:
                decoded_yaml = yaml_decode(file.read_bytes(), type=structs.AutomationDescriptor)
                parsed_yaml[decoded_yaml.automation_name] = decoded_yaml
            except (ValidationError, DecodeError) as e:
                publish_to_error_log(f"Yaml error in {Path(file).name}: {e}", "get_automation_contrib")

        return attach_cache_control(jsonify(list(parsed_yaml.values())))

    except Exception as e:
        publish_to_error_log(str(e), "get_automation_contrib")
        abort_with(400, str(e))


@api_bp.route("/contrib/jobs", methods=["GET"])
def get_job_contrib() -> ResponseReturnValue:
    try:
        job_path_builtins = Path(os.environ["DOT_PIOREACTOR"]) / "ui" / "jobs"
        job_path_plugins = Path(os.environ["DOT_PIOREACTOR"]) / "plugins" / "ui" / "jobs"
        files = sorted(job_path_builtins.glob("*.y*ml")) + sorted(job_path_plugins.glob("*.y*ml"))

        # we dedup based on 'job_name'.
        parsed_yaml = {}

        for file in files:
            try:
                decoded_yaml = yaml_decode(file.read_bytes(), type=structs.BackgroundJobDescriptor)
                parsed_yaml[decoded_yaml.job_name] = decoded_yaml
            except (ValidationError, DecodeError) as e:
                publish_to_error_log(f"Yaml error in {Path(file).name}: {e}", "get_job_contrib")

        return attach_cache_control(jsonify(list(parsed_yaml.values())))

    except Exception as e:
        publish_to_error_log(str(e), "get_job_contrib")
        abort_with(400, str(e))


@api_bp.route("/contrib/charts", methods=["GET"])
def get_charts_contrib() -> ResponseReturnValue:
    try:
        chart_path_builtins = Path(os.environ["DOT_PIOREACTOR"]) / "ui" / "charts"
        chart_path_plugins = Path(os.environ["DOT_PIOREACTOR"]) / "plugins" / "ui" / "charts"
        files = sorted(chart_path_builtins.glob("*.y*ml")) + sorted(chart_path_plugins.glob("*.y*ml"))

        # we dedup based on chart 'chart_key'.
        parsed_yaml = {}
        for file in files:
            try:
                decoded_yaml = yaml_decode(file.read_bytes(), type=structs.ChartDescriptor)
                parsed_yaml[decoded_yaml.chart_key] = decoded_yaml
            except (ValidationError, DecodeError) as e:
                publish_to_error_log(f"Yaml error in {Path(file).name}: {e}", "get_charts_contrib")

        return attach_cache_control(jsonify(list(parsed_yaml.values())))

    except Exception as e:
        publish_to_error_log(str(e), "get_charts_contrib")
        abort_with(400, str(e))


@api_bp.route("/system/update_next_version", methods=["POST"])
def update_app() -> DelayedResponseReturnValue:
    task = tasks.update_app_across_cluster()
    return create_task_response(task)


@api_bp.route("/system/update_from_archive", methods=["POST"])
def update_app_from_release_archive() -> DelayedResponseReturnValue:
    body = request.get_json()
    release_archive_location = body["release_archive_location"]
    assert release_archive_location.endswith(".zip")
    task = tasks.update_app_from_release_archive_across_cluster(release_archive_location, units=body["units"])
    return create_task_response(task)


@api_bp.route("/contrib/exportable_datasets", methods=["GET"])
def get_exportable_datasets() -> ResponseReturnValue:
    try:
        builtins = sorted((Path(os.environ["DOT_PIOREACTOR"]) / "exportable_datasets").glob("*.y*ml"))
        plugins = sorted(
            (Path(os.environ["DOT_PIOREACTOR"]) / "plugins" / "exportable_datasets").glob("*.y*ml")
        )
        parsed_yaml = []
        for file in builtins + plugins:
            try:
                dataset = yaml_decode(file.read_bytes(), type=Dataset)
                parsed_yaml.append(dataset)
            except (ValidationError, DecodeError) as e:
                publish_to_error_log(f"Yaml error in {Path(file).name}: {e}", "get_exportable_datasets")

        return attach_cache_control(jsonify(parsed_yaml), max_age=60)

    except Exception as e:
        publish_to_error_log(str(e), "get_exportable_datasets")
        abort_with(400, str(e))


@api_bp.route("/contrib/exportable_datasets/<target_dataset>/preview", methods=["GET"])
def preview_exportable_datasets(target_dataset) -> ResponseReturnValue:
    builtins = sorted((Path(os.environ["DOT_PIOREACTOR"]) / "exportable_datasets").glob("*.y*ml"))
    plugins = sorted((Path(os.environ["DOT_PIOREACTOR"]) / "plugins" / "exportable_datasets").glob("*.y*ml"))

    n_rows = request.args.get("n_rows", 5)

    for file in builtins + plugins:
        try:
            dataset = yaml_decode(file.read_bytes(), type=Dataset)
            if dataset.dataset_name == target_dataset:
                query = f"SELECT * FROM ({dataset.table or dataset.query}) LIMIT {n_rows};"
                result = query_app_db(query)
                return jsonify(result)
        except (ValidationError, DecodeError):
            pass
    abort_with(
        404,
        f"{target_dataset} not found",
        cause="Dataset name not found in built-in or plugin exportable datasets.",
        remediation="List exportable datasets and choose a valid dataset_name.",
    )


@api_bp.route("/contrib/exportable_datasets/export_datasets", methods=["POST"])
def export_datasets() -> ResponseReturnValue:
    body = request.get_json()

    dataset_names: list[str] = body["datasets"]

    experiments: list[str] = body["experiments"]
    partition_by_unit: bool = body["partition_by_unit"]
    partition_by_experiment: bool = body["partition_by_experiment"]

    timestamp = current_utc_datetime().strftime("%Y%m%d%H%M%S")
    filename = f"export_{timestamp}.zip"

    filename_with_path = Path(f"{os.environ['RUN_PIOREACTOR']}/exports/") / filename
    result = (
        tasks.export_experiment_data_task(  # uses a lock so multiple exports can't happen simultaneously.
            experiments if experiments[0] != "<All experiments>" else [],
            dataset_names,
            filename_with_path.as_posix(),
            start_time=body.get("start_time"),
            end_time=body.get("end_time"),
            partition_by_unit=partition_by_unit,
            partition_by_experiment=partition_by_experiment,
        )
    )
    try:
        status, msg = result(blocking=True, timeout=5 * 60)
    except (HueyException, TaskException):
        abort_with(
            500,
            "Export task failed or timed out",
            cause="Task error or timeout while exporting datasets.",
            remediation="Retry the export and check server logs if it persists.",
        )

    if not status:
        publish_to_error_log(msg, "export_datasets")
        abort_with(
            500,
            "Export task failed",
            cause=msg,
            remediation="Check server logs for details and retry the export.",
        )

    return {"result": status, "filename": filename, "msg": "Finished"}, 200


@api_bp.route("/experiments", methods=["GET"])
def get_experiments() -> ResponseReturnValue:
    try:
        response = jsonify(
            query_app_db(
                """SELECT experiment, created_at, description, round( (strftime("%s","now") - strftime("%s", created_at))/60/60, 0) as delta_hours
                FROM experiments
                ORDER BY created_at
                DESC;"""
            )
        )
        return response

    except Exception as e:
        publish_to_error_log(str(e), "get_experiments")
        abort_with(500, str(e))


@api_bp.route("/experiments", methods=["POST"])
def create_experiment() -> ResponseReturnValue:
    body = request.get_json()
    proposed_experiment_name = body.get("experiment")

    if not proposed_experiment_name:
        abort_with(
            400,
            "Experiment name is required",
            cause="Request JSON missing 'experiment'.",
            remediation="Provide an experiment name in the 'experiment' field.",
        )
    elif len(proposed_experiment_name) >= 200:  # just too big
        abort_with(
            400,
            "Experiment name is too long",
            cause="Experiment name exceeds 199 characters.",
            remediation="Shorten the experiment name to under 200 characters.",
        )
    elif proposed_experiment_name.lower() == "current":  # too much API rework
        abort_with(
            400,
            "Experiment name cannot be 'current'",
            cause="'current' is a reserved experiment identifier.",
            remediation="Choose a different experiment name.",
        )
    elif proposed_experiment_name.startswith("_testing"):  # jobs won't run as expected
        abort_with(
            400,
            "Experiment name cannot start with '_testing'",
            cause="Experiment names starting with '_testing' are reserved.",
            remediation="Choose a name that does not start with '_testing'.",
        )
    elif (
        ("#" in proposed_experiment_name)
        or ("+" in proposed_experiment_name)
        or ("$" in proposed_experiment_name)
        or ("/" in proposed_experiment_name)
        or ("%" in proposed_experiment_name)
        or ("\\" in proposed_experiment_name)
    ):
        abort_with(
            400,
            "Experiment name cannot contain special characters (#, $, %, +, /, \\)",
            cause="Experiment name contains disallowed characters.",
            remediation="Use letters, digits, spaces, dots, dashes, or underscores.",
        )

    try:
        row_count = modify_app_db(
            "INSERT INTO experiments (created_at, experiment, description, media_used, organism_used) VALUES (?,?,?,?,?)",
            (
                current_utc_timestamp(),
                proposed_experiment_name,
                body.get("description"),
                body.get("mediaUsed"),
                body.get("organismUsed"),
            ),
        )

        if row_count == 0:
            raise sqlite3.IntegrityError()

        publish_to_experiment_log(
            f"New experiment created: {body['experiment']}",
            proposed_experiment_name,
            "create_experiment",
            level="INFO",
        )
        return {"status": "success"}, 201

    except sqlite3.IntegrityError:
        abort_with(
            409,
            "Experiment already exists",
            cause="Experiment name conflicts with an existing experiment.",
            remediation="Choose a different experiment name and retry.",
        )
    except Exception as e:
        publish_to_error_log(str(e), "create_experiment")
        abort_with(500, str(e))


@api_bp.route("/experiments/<experiment>", methods=["DELETE"])
def delete_experiment(experiment: str) -> ResponseReturnValue:
    row_count = modify_app_db("DELETE FROM experiments WHERE experiment=?;", (experiment,))
    broadcast_post_across_cluster("/unit_api/jobs/stop", json={"experiment": experiment})

    if row_count > 0:
        try:
            # Reclaim the freed pages from the cascaded delete.
            modify_app_db("VACUUM;")
        except sqlite3.OperationalError:
            pass
        finally:
            return {"status": "success"}, 200
    else:
        abort_with(
            404,
            f"Experiment {experiment} not found",
            cause="Experiment name not found in database.",
            remediation="List experiments and choose a valid experiment name.",
        )


@api_bp.route("/experiments/latest", methods=["GET"])
def get_latest_experiment() -> ResponseReturnValue:
    try:
        return attach_cache_control(
            jsonify(
                query_app_db(
                    "SELECT experiment, created_at, description, media_used, organism_used, delta_hours FROM latest_experiment",
                    one=True,
                )
            ),
            max_age=2,
        )

    except Exception as e:
        publish_to_error_log(str(e), "get_latest_experiment")
        abort_with(500, str(e))


@api_bp.route("/experiments/<experiment>/unit_labels", methods=["GET"])
def get_unit_labels(experiment: str) -> ResponseReturnValue:
    try:
        if experiment == "current":
            unit_labels = query_app_db(
                "SELECT r.pioreactor_unit as unit, r.label FROM pioreactor_unit_labels AS r JOIN latest_experiment USING (experiment);"
            )
        else:
            unit_labels = query_app_db(
                "SELECT r.pioreactor_unit as unit, r.label FROM pioreactor_unit_labels as r WHERE experiment=?;",
                (experiment,),
            )

        assert isinstance(unit_labels, list)

        keyed_by_unit = {d["unit"]: d["label"] for d in unit_labels}

        return attach_cache_control(jsonify(keyed_by_unit), max_age=10)

    except Exception as e:
        publish_to_error_log(str(e), "get_unit_labels")
        abort_with(500, str(e))


@api_bp.route("/experiments/<experiment>/unit_labels", methods=["PUT", "PATCH"])
def upsert_unit_labels(experiment: str) -> ResponseReturnValue:
    """
    Update or insert a new unit label for the current experiment.


    JSON Request Body:
    {
        "unit": "<unit_identifier>",
        "label": "<new_label>"
    }

    Example usage:
    PUT /api/experiments/demo/unit_labels
    {
        "unit": "unit1",
        "label": "new_label"
    }

    """

    body = request.get_json()

    unit = body["unit"]
    label = body["label"]

    try:
        if (
            label == ""
        ):  # empty string, eg they are removing the label. We can't use the upsert below since then multiple workers are assigned "" and our unique constraint prevents that.
            modify_app_db(
                "DELETE FROM pioreactor_unit_labels WHERE experiment=(?) AND pioreactor_unit = (?)",
                (experiment, unit),
            )
        else:
            modify_app_db(
                "INSERT OR REPLACE INTO pioreactor_unit_labels (label, experiment, pioreactor_unit, created_at) VALUES ((?), (?), (?), STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW') ) ON CONFLICT(experiment, pioreactor_unit) DO UPDATE SET label=excluded.label, created_at=STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')",
                (label, experiment, unit),
            )

    except Exception as e:
        publish_to_error_log(str(e), "upsert_current_unit_labels")
        abort_with(400, str(e))

    return {"status": "success"}, 201


@api_bp.route("/historical_organisms", methods=["GET"])
def get_historical_organisms_used() -> ResponseReturnValue:
    try:
        historical_organisms = query_app_db(
            'SELECT DISTINCT organism_used as key FROM experiments WHERE NOT (organism_used IS NULL OR organism_used == "") ORDER BY created_at DESC;'
        )

    except Exception as e:
        publish_to_error_log(str(e), "historical_organisms")
        abort_with(500, str(e))

    return jsonify(historical_organisms)


@api_bp.route("/historical_media", methods=["GET"])
def get_historical_media_used() -> ResponseReturnValue:
    try:
        historical_media = query_app_db(
            'SELECT DISTINCT media_used as key FROM experiments WHERE NOT (media_used IS NULL OR media_used == "") ORDER BY created_at DESC;'
        )

    except Exception as e:
        publish_to_error_log(str(e), "historical_media")
        abort_with(500, str(e))

    return jsonify(historical_media)


@api_bp.route("/experiments/<experiment>", methods=["PATCH"])
def update_experiment(experiment: str) -> ResponseReturnValue:
    body = request.get_json()
    if "description" in body:
        row_count = modify_app_db(
            "UPDATE experiments SET description = (?) WHERE experiment=(?)",
            (body["description"], experiment),
        )

        if row_count == 1:
            return {"status": "success"}, 200
        else:
            abort_with(404, f"Experiment {experiment} not found")
    else:
        abort_with(400, "Missing description")


@api_bp.route("/experiments/<experiment>", methods=["GET"])
def get_experiment(experiment: str) -> ResponseReturnValue:
    result = query_app_db(
        """SELECT experiment, created_at, description, round( (strftime("%s","now") - strftime("%s", created_at))/60/60, 0) as delta_hours
        FROM experiments
        WHERE experiment=(?);
        """,
        (experiment,),
        one=True,
    )
    if result is not None:
        return jsonify(result)
    else:
        abort_with(404, f"Experiment {experiment} not found")


## CONFIG CONTROL


@api_bp.route("/units/<pioreactor_unit>/configuration", methods=["GET"])
def get_configuration_for_pioreactor_unit(pioreactor_unit: str) -> ResponseReturnValue:
    """get configuration for a pioreactor unit"""
    if pioreactor_unit == UNIVERSAL_IDENTIFIER:
        pioreactor_units = get_all_units()
    else:
        pioreactor_units = [pioreactor_unit]

    result: dict[str, dict[str, dict]] = {}

    for unit in pioreactor_units:
        try:
            global_config_path = Path(os.environ["DOT_PIOREACTOR"]) / "config.ini"

            specific_config_path = Path(os.environ["DOT_PIOREACTOR"]) / f"config_{pioreactor_unit}.ini"

            config_files = [global_config_path, specific_config_path]
            config = configparser.ConfigParser(strict=False)
            config.read(config_files)

            result[unit] = {section: dict(config[section]) for section in config.sections()}

        except Exception as e:
            publish_to_error_log(str(e), "get_configuration_for_pioreactor_unit")
            abort_with(400, str(e))

    return result


@api_bp.route("/configs/<filename>", methods=["GET"])
def get_config(filename: str) -> ResponseReturnValue:
    """get a specific config.ini file in the .pioreactor folder"""

    # security bit: strip out any paths that may be attached, ex: ../../../root/bad
    filename = Path(filename).name

    try:
        if Path(filename).suffix != ".ini":
            abort_with(400, "Must be a .ini file")

        specific_config_path = Path(os.environ["DOT_PIOREACTOR"]) / filename

        return attach_cache_control(
            Response(
                response=specific_config_path.read_text(),
                status=200,
                mimetype="text/plain",
            ),
            max_age=10,
        )

    except Exception as e:
        publish_to_error_log(str(e), "get_config_of_file")
        abort_with(400, str(e))


@api_bp.route("/configs", methods=["GET"])
def get_configs() -> ResponseReturnValue:
    """get a list of all config.ini files in the .pioreactor folder, _and_ are part of the inventory _or_ are leader"""

    all_workers = query_app_db("SELECT pioreactor_unit FROM workers;")
    assert isinstance(all_workers, list)
    workers_bucket = {worker["pioreactor_unit"] for worker in all_workers}
    leader_bucket = {
        get_leader_hostname()
    }  # should be same as current HOSTNAME since this runs on the leader.
    pioreactors_bucket = workers_bucket | leader_bucket

    def strip_worker_name_from_config(file_name):
        return file_name.removeprefix("config_").removesuffix(".ini")

    def allow_file_through(file_name: str):
        if file_name == "config.ini":
            return True
        else:
            # return True
            return strip_worker_name_from_config(file_name) in pioreactors_bucket

    config_path = Path(os.environ["DOT_PIOREACTOR"])
    return jsonify(
        [file.name for file in sorted(config_path.glob("config*.ini")) if allow_file_through(file.name)]
    )


@api_bp.route("/configs/<filename>", methods=["PATCH"])
def update_config(filename: str) -> ResponseReturnValue:
    body = request.get_json()
    code = body["code"]

    if not filename.endswith(".ini"):
        return abort_with(400, "Incorrect filetype. Must be .ini.")

    # security bit:
    # users could have filename look like ../../../../root/bad.txt
    # the below code will strip any paths.
    # General security risk here is ability to save arbitrary file to OS.
    filename = Path(filename).name

    # is the user editing a worker config or the global config?
    regex = re.compile(r"config_?(.*)?\.ini")
    is_unit_specific = regex.match(filename)
    assert is_unit_specific is not None

    if is_unit_specific[1] != "":
        units = is_unit_specific[1]
        flags = ("--specific",)
    else:
        units = UNIVERSAL_IDENTIFIER
        flags = ("--shared",)

    # General security risk here to save arbitrary file to OS.
    config_path = Path(os.environ["DOT_PIOREACTOR"]) / filename

    # can the config actually be read? ex. no repeating sections, typos, etc.
    # filename is a string
    config = configparser.ConfigParser(allow_no_value=True)

    # make unicode replacements
    # https://github.com/Pioreactor/pioreactor/issues/539
    code = code.replace(chr(8211), chr(45))  # en-dash to dash
    code = code.replace(chr(8212), chr(45))  # em

    try:
        config.read_string(code)  # test parser

        # if editing config.ini (not a unit specific)
        # test to make sure we have minimal code to run pio commands
        if filename == "config.ini":
            assert config["cluster.topology"]
            assert config.get("cluster.topology", "leader_hostname")
            assert config.get("cluster.topology", "leader_address")
            assert config["mqtt"]

        if config.get("cluster.topology", "leader_address", fallback="").startswith("http") or config.get(
            "mqtt", "broker_address", fallback=""
        ).startswith("http"):
            abort_with(400, "Don't start addresses with http:// or https://")

    except configparser.DuplicateSectionError as e:
        msg = f"Duplicate section [{e.section}] was found. Please fix and try again."
        publish_to_error_log(msg, "update_config")
        abort_with(400, msg)
    except configparser.DuplicateOptionError as e:
        msg = f"Duplicate option, `{e.option}`, was found in section [{e.section}]. Please fix and try again."
        publish_to_error_log(msg, "update_config")
        abort_with(400, msg)
    except configparser.ParsingError:
        msg = "Incorrect syntax. Please fix and try again."
        publish_to_error_log(msg, "update_config")
        abort_with(400, msg)
    except (AssertionError, configparser.NoSectionError, KeyError) as e:
        msg = f"Missing required field(s): {e}"
        publish_to_error_log(msg, "update_config")
        abort_with(400, msg)
    except ValueError as e:
        msg = str(e)
        publish_to_error_log(msg, "update_config")
        abort_with(400, msg)
    except Exception as e:
        publish_to_error_log(str(e), "update_config")
        msg = "Hm, something went wrong, check Pioreactor logs."
        abort_with(500, msg)

    # if the config file is unit specific, we only need to run sync-config on that unit.
    result = tasks.write_config_and_sync(config_path, code, units, flags)

    try:
        status, msg_or_exception = result(blocking=True, timeout=75)
    except (HueyException, TaskException):
        status, msg_or_exception = False, "sync-configs timed out."

    if not status:
        publish_to_error_log(msg_or_exception, "save_new_config")
        abort_with(500, str(msg_or_exception))

    return {"status": "success"}, 200


@api_bp.route("/configs/<filename>/history", methods=["GET"])
def get_historical_config_for(filename: str) -> ResponseReturnValue:
    configs_for_filename = query_app_db(
        "SELECT filename, timestamp, data FROM config_files_histories WHERE filename=? ORDER BY timestamp DESC",
        (filename,),
    )

    return attach_cache_control(jsonify(configs_for_filename), max_age=15)


@api_bp.route("/is_local_access_point_active", methods=["GET"])
def is_local_access_point_active() -> ResponseReturnValue:
    return attach_cache_control(
        jsonify({"result": os.path.isfile("/boot/firmware/local_access_point")}), max_age=10_000
    )


### experiment profiles


@api_bp.route("/experiment_profiles/running/experiments/<experiment>", methods=["GET"])
def get_running_profiles(experiment: str) -> ResponseReturnValue:
    jobs = query_temp_local_metadata_db(
        """
        SELECT
            json_group_array(json_object(
                'job_name', m.job_name,
                'experiment', m.experiment,
                'job_id', m.job_id,
                'settings', (
                    SELECT json_group_object(s.setting, s.value)
                    FROM pio_job_published_settings s
                    WHERE s.job_id = m.job_id
                )
            )) as result
        FROM
            pio_job_metadata m
        WHERE
            m.is_running=1 and
            m.experiment = (?) AND
            m.job_name="experiment_profile"
        """,
        (experiment,),
        one=True,
    )
    assert isinstance(jobs, dict)

    return as_json_response(jobs["result"])


@api_bp.route("/experiments/<experiment>/experiment_profiles/recent", methods=["GET"])
def get_recent_experiment_profile_runs(experiment: str) -> ResponseReturnValue:
    recent_runs = query_app_db(
        """
        SELECT started_at, experiment_profile_name, experiment
        FROM experiment_profile_runs
        WHERE experiment = ?
        ORDER BY datetime(started_at) DESC
        """,
        (experiment,),
    )

    return attach_cache_control(jsonify(recent_runs), max_age=5)


@api_bp.route("/contrib/experiment_profiles", methods=["POST"])
def create_experiment_profile() -> ResponseReturnValue:
    body = request.get_json()
    experiment_profile_body = body["body"]
    experiment_profile_filename = Path(body["filename"]).name

    # verify content
    try:
        yaml_decode(experiment_profile_body, type=Profile)
    except Exception as e:
        msg = f"{e}"
        # publish_to_error_log(msg, "create_experiment_profile")
        return abort_with(400, msg)

    # verify file
    try:
        if not is_valid_unix_filename(experiment_profile_filename):
            abort_with(400, "Not valid unix name")

        if not (
            experiment_profile_filename.endswith(".yaml") or experiment_profile_filename.endswith(".yml")
        ):
            abort_with(400, "must end in .yaml")

    except Exception:
        msg = "Invalid filename"
        # publish_to_error_log(msg, "create_experiment_profile")
        abort_with(400, msg)

    filepath = Path(os.environ["DOT_PIOREACTOR"]) / "experiment_profiles" / experiment_profile_filename

    # check if exists
    if filepath.exists():
        abort_with(400, "A profile already exists with that filename. Choose another.")

    # save file to disk
    tasks.save_file(
        filepath,
        experiment_profile_body,
    )

    return {"status": "success"}, 200


@api_bp.route("/contrib/experiment_profiles", methods=["PATCH"])
def update_experiment_profile() -> ResponseReturnValue:
    body = request.get_json()
    experiment_profile_body = body["body"]
    experiment_profile_filename = Path(body["filename"]).name

    # verify content
    try:
        yaml_decode(experiment_profile_body, type=Profile)
    except Exception as e:
        # publish_to_error_log(msg, "create_experiment_profile")
        abort_with(400, str(e))

    # verify file - user could have provided a different filename so we still check this.
    try:
        if not is_valid_unix_filename(experiment_profile_filename):
            abort_with(400, "not valid unix filename")

        if not (
            experiment_profile_filename.endswith(".yaml") or experiment_profile_filename.endswith(".yml")
        ):
            abort_with(400, "must end in .yaml")

    except Exception as e:
        # publish_to_error_log(msg, "create_experiment_profile")
        abort_with(400, str(e))

    filepath = Path(os.environ["DOT_PIOREACTOR"]) / "experiment_profiles" / experiment_profile_filename

    # save file to disk
    tasks.save_file(
        filepath,
        experiment_profile_body,
    )

    return {"status": "success"}, 200


@api_bp.route("/contrib/experiment_profiles", methods=["GET"])
def get_experiment_profiles() -> ResponseReturnValue:
    try:
        profile_path = Path(os.environ["DOT_PIOREACTOR"]) / "experiment_profiles"
        files = sorted(profile_path.glob("*.y*ml"), key=lambda f: f.stat().st_mtime, reverse=True)

        parsed_yaml = []
        for file in files:
            # allow empty files, it's annoying to users otherwise (and maybe theres a bug that wipes yamls?)
            if file.stat().st_size == 0:
                parsed_yaml.append(
                    {
                        "experimentProfile": Profile(experiment_profile_name=f"temporary name: {file.stem}"),
                        "file": Path(file).name,
                        "fullpath": Path(file).as_posix(),
                    }
                )
                continue

            try:
                profile = yaml_decode(file.read_bytes(), type=Profile)
                parsed_yaml.append(
                    {
                        "experimentProfile": profile,
                        "file": Path(file).name,
                        "fullpath": Path(file).as_posix(),
                    }
                )
            except (ValidationError, DecodeError) as e:
                publish_to_error_log(f"Yaml error in {Path(file).name}: {e}", "get_experiment_profiles")

        return attach_cache_control(jsonify(parsed_yaml), max_age=5)
    except Exception as e:
        publish_to_error_log(str(e), "get_experiment_profiles")
        abort_with(400, str(e))


@api_bp.route("/contrib/experiment_profiles/<filename>", methods=["GET"])
def get_experiment_profile(filename: str) -> ResponseReturnValue:
    file = Path(filename).name
    try:
        if not (Path(file).suffix == ".yaml" or Path(file).suffix == ".yml"):
            raise IOError("must provide a YAML file")

        specific_profile_path = Path(os.environ["DOT_PIOREACTOR"]) / "experiment_profiles" / file
        return Response(
            response=specific_profile_path.read_text(),
            status=200,
            mimetype="text/plain",
        )
    except IOError as e:
        publish_to_error_log(str(e), "get_experiment_profile")
        abort_with(404, str(e))


@api_bp.route("/contrib/experiment_profiles/<filename>", methods=["DELETE"])
def delete_experiment_profile(filename: str) -> ResponseReturnValue:
    file = Path(filename).name
    try:
        if Path(file).suffix not in (".yaml", ".yml"):
            raise IOError("must provide a YAML file")

        specific_profile_path = Path(os.environ["DOT_PIOREACTOR"]) / "experiment_profiles" / file
        tasks.rm(specific_profile_path)
        publish_to_log(f"Deleted profile {filename}.", "delete_experiment_profile")
        return {"status": "success"}, 200
    except IOError as e:
        publish_to_error_log(str(e), "delete_experiment_profile")
        abort_with(404, str(e))
    except Exception as e:
        publish_to_error_log(str(e), "delete_experiment_profile")
        abort_with(500, str(e))


##### Worker endpoints


@api_bp.route("/units", methods=["GET"])
def get_list_of_units() -> ResponseReturnValue:
    # Get a list of all units (workers + leader)
    all_units = get_all_units()
    return jsonify([{"pioreactor_unit": u} for u in all_units])


@api_bp.route("/workers", methods=["GET"])
def get_list_of_workers() -> ResponseReturnValue:
    # Get a list of all workers
    all_workers = query_app_db(
        "SELECT pioreactor_unit, added_at, is_active, model_name, model_version FROM workers ORDER BY pioreactor_unit;"
    )
    return jsonify(all_workers)


@api_bp.route("/workers/discover", methods=["GET"])
def discover_available_workers() -> ResponseReturnValue:
    """
    Discover available pioreactor workers on the network not already registered.
    """
    from pioreactor.utils.networking import discover_workers_on_network

    discovered_hosts = list(discover_workers_on_network(terminate=True))
    existing = get_all_workers()
    available = [h for h in discovered_hosts if h not in existing]
    return jsonify([{"pioreactor_unit": h} for h in available])


@api_bp.route("/workers/setup", methods=["POST"])
def setup_worker_pioreactor() -> ResponseReturnValue:
    data = request.get_json()
    new_name = data["name"]
    version = data["version"]
    model = data["model"]

    try:
        result = tasks.add_new_pioreactor(new_name, version, model)
    except Exception as e:
        return abort_with(404, str(e))

    try:
        status = result(blocking=True, timeout=250)
    except (HueyException, TaskException):
        status = False

    if status:
        return {"msg": f"Worker {new_name} added successfully."}, 200
    else:
        abort_with(404, f"Failed to add worker {new_name}. See logs.")


@api_bp.route("/workers", methods=["PUT"])
def add_worker() -> ResponseReturnValue:
    data = request.get_json()
    pioreactor_unit = data.get("pioreactor_unit")
    model_name = data.get("model_name")  # optional
    model_version = data.get("model_version")  # optional

    if not pioreactor_unit:
        abort_with(
            400,
            "Missing unit name",
            cause="Request JSON missing 'pioreactor_unit'.",
            remediation="Provide a pioreactor_unit in the JSON payload.",
        )

    nrows = modify_app_db(
        "INSERT OR REPLACE INTO workers (pioreactor_unit, added_at, is_active, model_name, model_version) VALUES (?, STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'), 1, ?, ?);",
        (pioreactor_unit, model_name, model_version),
    )
    if nrows > 0:
        return {"status": "success"}, 201
    else:
        abort_with(
            500,
            "Failed to add worker to database.",
            cause="Failed to insert worker into database.",
            remediation="Check database logs and retry.",
        )


@api_bp.route("/workers/<pioreactor_unit>", methods=["DELETE"])
def delete_worker(pioreactor_unit: str) -> ResponseReturnValue:
    row_count = modify_app_db("DELETE FROM workers WHERE pioreactor_unit=?;", (pioreactor_unit,))
    if row_count > 0:
        tasks.multicast_post("/unit_api/jobs/stop/all", [pioreactor_unit])

        # only delete configs if not the leader...
        if pioreactor_unit != HOSTNAME:
            unit_config = f"config_{pioreactor_unit}.ini"

            # delete config on disk
            config_path = Path(os.environ["DOT_PIOREACTOR"]) / unit_config
            tasks.rm(config_path)

            # delete from histories
            modify_app_db("DELETE FROM config_files_histories WHERE filename=?;", (unit_config,))

            # delete configs on worker
            tasks.multicast_post(
                "/unit_api/system/remove_file",
                [pioreactor_unit],
                json={"filepath": str(Path(os.environ["DOT_PIOREACTOR"]) / "config.ini")},
            )
            tasks.multicast_post(
                "/unit_api/system/remove_file",
                [pioreactor_unit],
                json={"filepath": str(Path(os.environ["DOT_PIOREACTOR"]) / "unit_config.ini")},
            )

        publish_to_log(
            f"Removed {pioreactor_unit} from inventory.",
            level="INFO",
            task="assignment",
        )

        return {"status": "success"}, 202
    else:
        abort_with(
            404,
            f"Worker {pioreactor_unit} not found",
            cause="Worker name not found in database.",
            remediation="Check the unit name or add the worker to the inventory.",
        )


@api_bp.route("/workers/<pioreactor_unit>/is_active", methods=["PUT"])
def change_worker_status(pioreactor_unit: str) -> ResponseReturnValue:
    # Get the new status from the request body
    data = request.get_json()
    new_status = data.get("is_active")

    if new_status not in [0, 1]:
        abort_with(
            400,
            "Invalid status. Status must be integer 0 or 1.",
            cause=f"Received status '{new_status}'.",
            remediation="Send is_active as 0 or 1.",
        )

    # Update the status of the worker in the database
    row_count = modify_app_db(
        "UPDATE workers SET is_active = (?) WHERE pioreactor_unit = (?)",
        (new_status, pioreactor_unit),
    )

    if row_count > 0:
        publish_to_log(
            f"Set {pioreactor_unit} to {'Active' if new_status else 'Inactive'}.",
            task="worker_status",
            level="INFO",
        )
        if new_status == 0:
            tasks.multicast_post("/unit_api/jobs/stop/all", [pioreactor_unit])
        return {"status": "success"}, 200
    else:
        abort_with(
            404,
            f"Worker {pioreactor_unit} not found",
            cause="Worker name not found in database.",
            remediation="Check the unit name or add the worker to the inventory.",
        )


@api_bp.route("/workers/<pioreactor_unit>/model", methods=["PUT"])
def change_worker_model(pioreactor_unit: str) -> ResponseReturnValue:
    # Get the new status from the request body
    data = request.get_json()
    model_version, model_name = data.get("model_version"), data.get("model_name")

    if not model_version or not model_name:
        abort_with(
            400,
            "Missing model_version or model_name",
            cause="Request JSON missing model_version or model_name.",
            remediation="Provide both model_name and model_version in the JSON payload.",
        )

    if (model_name, model_version) not in get_registered_models():
        abort_with(
            400,
            "Model name or version not found in available models.",
            cause=f"Unknown model '{model_name}' with version '{model_version}'.",
            remediation="Use a model_name and model_version from the registered models list.",
        )

    # Update the status of the worker in the database
    row_count = modify_app_db(
        "UPDATE workers SET model_name = (?), model_version= (?) WHERE pioreactor_unit = (?)",
        (model_name, model_version, pioreactor_unit),
    )

    if row_count > 0:
        publish_to_log(
            f"Set {pioreactor_unit} to {model_name}, {model_version}.",
            task="worker_model",
            level="INFO",
        )
        # When new model versions are added, consider extending hardware checks here
        # (see /unit_api/hardware/check and tasks.check_model_hardware).
        if model_version == "1.5":
            tasks.post_into_unit(
                pioreactor_unit,
                "/unit_api/hardware/check",
                json={"model_name": model_name, "model_version": model_version},
            )
        return {"status": "success"}, 200
    else:
        abort_with(
            404,
            f"Worker {pioreactor_unit} not found",
            cause="Worker name not found in database.",
            remediation="Check the unit name or add the worker to the inventory.",
        )


@api_bp.route("/workers/<pioreactor_unit>/model", methods=["GET"])
def get_worker_model_and_metadata(pioreactor_unit: str) -> ResponseReturnValue:
    # Query the database for a worker's model and metadata
    result = query_app_db(
        """
        SELECT pioreactor_unit, model_name, model_version
        FROM workers
        WHERE pioreactor_unit = ?
        """,
        (pioreactor_unit,),
        one=True,
    )
    if result is None:
        # If the worker is not found, return an error
        return abort_with(
            404,
            "Worker not found",
            cause="Worker name not found in database.",
            remediation="Check the unit name or add the worker to the inventory.",
        )
    else:
        assert isinstance(result, dict)
        # If the worker is found, return the model and metadata
        return attach_cache_control(
            jsonify(
                {
                    "pioreactor_unit": result["pioreactor_unit"],
                    "model_name": result["model_name"],
                    "model_version": result["model_version"],
                    **to_builtins(get_registered_models()[(result["model_name"], result["model_version"])]),
                }
            )
        )


@api_bp.route("/workers/<pioreactor_unit>", methods=["GET"])
def get_worker(pioreactor_unit: str) -> ResponseReturnValue:
    # Query the database for a worker
    result = query_app_db(
        """
        SELECT pioreactor_unit, added_at, is_active, model_name, model_version
        FROM workers
        WHERE pioreactor_unit = ?
        """,
        (pioreactor_unit,),
        one=True,
    )

    # Check if the worker is found and assigned to the experiment
    if result:
        return jsonify(result)
    else:
        abort_with(
            404,
            "Worker not found",
            cause=f"Worker '{pioreactor_unit}' not in leader database.",
            remediation="Check the unit name or add the worker to the inventory.",
        )


### Experiment worker assignments


@api_bp.route("/workers/assignments", methods=["GET"])
def get_workers_and_experiment_assignments() -> ResponseReturnValue:
    # Get the experiment that a worker is assigned to along with its status
    result = query_app_db(
        """
        SELECT w.pioreactor_unit, a.experiment, w.is_active
        FROM workers w
        LEFT JOIN experiment_worker_assignments a
          on w.pioreactor_unit = a.pioreactor_unit
        ORDER BY w.pioreactor_unit
        """,
    )
    if result:
        return attach_cache_control(jsonify(result), max_age=2)
    else:
        return attach_cache_control(jsonify([]), max_age=2)


@api_bp.route("/experiments/active", methods=["GET"])
def get_active_experiments() -> ResponseReturnValue:
    """Get list of experiments with at least one active worker assigned"""
    try:
        # same columns as GET /api/experiments, filtered to experiments with ≥1 active worker
        result = query_app_db(
            """
            SELECT
              e.experiment,
              e.created_at,
              e.description,
              round((strftime('%s','now') - strftime('%s', e.created_at))/60/60, 0) AS delta_hours
            FROM experiments e
            JOIN experiment_worker_assignments a
              ON e.experiment = a.experiment
            JOIN workers w
              ON a.pioreactor_unit = w.pioreactor_unit
            WHERE w.is_active = 1
            GROUP BY e.experiment, e.created_at, e.description
            ORDER BY e.created_at DESC
            """,
        )
        return attach_cache_control(jsonify(result or []), max_age=2)
    except Exception as e:
        publish_to_error_log(str(e), "get_active_experiments")
        abort_with(500, str(e))


@api_bp.route("/workers/assignments", methods=["DELETE"])
def remove_all_workers_from_all_experiments() -> DelayedResponseReturnValue:
    # unassign all
    modify_app_db(
        "DELETE FROM experiment_worker_assignments",
    )
    task = broadcast_post_across_workers("/unit_api/jobs/stop/all")
    publish_to_log(
        "Removed all worker assignments.",
        level="INFO",
        task="unassignment",
    )

    return create_task_response(task)


@api_bp.route("/experiments/assignment_count", methods=["GET"])
def get_experiments_worker_assignments() -> ResponseReturnValue:
    # Get the number of pioreactors assigned to an experiment.
    result = query_app_db(
        """
        SELECT e.experiment, count(a.pioreactor_unit) as worker_count
        FROM experiments e
        JOIN experiment_worker_assignments a
          on e.experiment = a.experiment
        JOIN workers w -- make sure the worker is still part of the inventory
          on w.pioreactor_unit = a.pioreactor_unit
        GROUP BY 1
        HAVING count(a.pioreactor_unit) > 0
        """,
    )
    if result:
        return attach_cache_control(jsonify(result), max_age=2)
    else:
        return attach_cache_control(jsonify([]), max_age=2)


@api_bp.route("/workers/<pioreactor_unit>/experiment", methods=["GET"])
def get_experiment_assignment_for_worker(pioreactor_unit: str) -> ResponseReturnValue:
    # Get the experiment that a worker is assigned to along with its active status
    result = query_app_db(
        """
        SELECT w.pioreactor_unit, w.is_active, a.experiment, w.model_name, w.model_version
        FROM workers w
        LEFT JOIN experiment_worker_assignments a
          on w.pioreactor_unit = a.pioreactor_unit
        WHERE w.pioreactor_unit = ?
        """,
        (pioreactor_unit,),
        one=True,
    )
    assert isinstance(result, dict | None)
    if result is None:
        abort_with(
            404,
            f"Worker {pioreactor_unit} not found.",
            cause=f"Worker '{pioreactor_unit}' not in leader database.",
            remediation="Check the unit name or add the worker to the inventory.",
        )
    elif result["experiment"] is None:  # type: ignore
        abort_with(
            404,
            f"Worker `{pioreactor_unit}` is not assigned to any experiment.",
            cause=f"No experiment assignment for worker '{pioreactor_unit}'.",
            remediation="Assign the worker to an experiment before querying its assignment.",
        )
    else:
        return attach_cache_control(jsonify(result), max_age=2)


@api_bp.route("/experiments/<experiment>/workers", methods=["GET"])
def get_list_of_workers_for_experiment(experiment: str) -> ResponseReturnValue:
    workers = query_app_db(
        """
        SELECT w.pioreactor_unit, w.is_active, w.model_name, w.model_version
        FROM experiment_worker_assignments a
        JOIN workers w
          on w.pioreactor_unit = a.pioreactor_unit
        WHERE experiment = ?
        ORDER BY w.pioreactor_unit
        """,
        (experiment,),
    )
    return attach_cache_control(jsonify(workers), max_age=2)


@api_bp.route("/experiments/<experiment>/historical_worker_assignments", methods=["GET"])
def get_list_of_historical_workers_for_experiment(experiment: str) -> ResponseReturnValue:
    workers = query_app_db(
        """
         SELECT pioreactor_unit, experiment, MAX(unassigned_at is NULL) as is_currently_assigned_to_experiment
         FROM experiment_worker_assignments_history
         WHERE experiment=?
         GROUP by 1,2;
        """,
        (experiment,),
    )
    return jsonify(workers)


@api_bp.route("/experiments/<experiment>/workers", methods=["PUT"])
def add_worker_to_experiment(experiment: str) -> ResponseReturnValue:
    # assign
    data = request.get_json()
    pioreactor_unit = data.get("pioreactor_unit")
    if not pioreactor_unit:
        abort_with(
            400,
            "Missing pioreactor_unit",
            cause="Request JSON missing 'pioreactor_unit'.",
            remediation="Provide a pioreactor_unit in the JSON payload.",
        )

    row_counts = modify_app_db(
        "INSERT OR REPLACE INTO experiment_worker_assignments (pioreactor_unit, experiment, assigned_at) VALUES (?, ?, STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))",
        (pioreactor_unit, experiment),
    )
    if row_counts > 0:
        publish_to_experiment_log(
            f"Assigned {pioreactor_unit} to {experiment}.",
            experiment=experiment,
            task="assignment",
            level="INFO",
        )

        return {"status": "success"}, 200
    else:
        # probably an integrity error
        abort_with(
            500,
            "Failed to add to database.",
            cause="Failed to insert assignment into database.",
            remediation="Check database logs and retry.",
        )


@api_bp.route("/experiments/<experiment>/workers/<pioreactor_unit>", methods=["DELETE"])
def remove_worker_from_experiment(experiment: str, pioreactor_unit: str) -> ResponseReturnValue:
    # unassign
    row_count = modify_app_db(
        "DELETE FROM experiment_worker_assignments WHERE pioreactor_unit = ? AND experiment = ?",
        (pioreactor_unit, experiment),
    )
    if row_count > 0:
        tasks.multicast_post("/unit_api/jobs/stop", [pioreactor_unit], json={"experiment": experiment})
        publish_to_experiment_log(
            f"Removed {pioreactor_unit} from {experiment}.",
            experiment=experiment,
            level="INFO",
            task="assignment",
        )
        return {"status": "success"}, 200
    else:
        abort_with(
            404,
            f"Worker {pioreactor_unit} not found",
            cause="Worker name not found in database or not assigned to experiment.",
            remediation="Check the unit name and assignment, then retry.",
        )


@api_bp.route("/experiments/<experiment>/workers", methods=["DELETE"])
def remove_workers_from_experiment(experiment: str) -> DelayedResponseReturnValue:
    # unassign all from specific experiment
    modify_app_db(
        "DELETE FROM experiment_worker_assignments WHERE experiment = ?",
        (experiment,),
    )
    task = broadcast_post_across_workers("/unit_api/jobs/stop", json={"experiment": experiment})
    publish_to_experiment_log(
        f"Removed all workers from {experiment}.",
        experiment=experiment,
        level="INFO",
        task="assignment",
    )

    return create_task_response(task)
