# -*- coding: utf-8 -*-
import json
import os
import zipfile
from functools import wraps
from io import BytesIO
from pathlib import Path
from subprocess import run
from tempfile import NamedTemporaryFile
from time import sleep
from typing import Any

from flask import after_this_request
from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from flask import Response
from flask import send_file
from flask.typing import ResponseReturnValue
from huey.exceptions import HueyException
from huey.exceptions import TaskException
from huey.exceptions import TaskLockedException
from msgspec import to_builtins
from msgspec.yaml import decode as yaml_decode
from pioreactor import structs
from pioreactor import whoami
from pioreactor.calibrations import CALIBRATION_PATH
from pioreactor.calibrations import get_calibration_protocols as get_calibration_protocols_registry
from pioreactor.config import get_leader_hostname
from pioreactor.estimators import ESTIMATOR_PATH
from pioreactor.models import get_registered_models
from pioreactor.structs import CalibrationBase
from pioreactor.structs import subclass_union
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import to_datetime
from pioreactor.version import __version__
from pioreactor.web import tasks
from pioreactor.web.app import HOSTNAME
from pioreactor.web.app import publish_to_error_log
from pioreactor.web.app import publish_to_log
from pioreactor.web.app import query_temp_local_metadata_db
from pioreactor.web.config import huey
from pioreactor.web.plugin_registry import registered_unit_api_routes
from pioreactor.web.unit_calibration_sessions_api import register_calibration_session_routes
from pioreactor.web.utils import abort_with
from pioreactor.web.utils import attach_cache_control
from pioreactor.web.utils import create_task_response
from pioreactor.web.utils import DelayedResponseReturnValue
from pioreactor.web.utils import is_rate_limited
from pioreactor.web.utils import is_valid_unix_filename
from werkzeug.utils import safe_join

AllCalibrations = subclass_union(CalibrationBase)
AllEstimators = subclass_union(structs.EstimatorBase)

unit_api_bp = Blueprint("unit_api", __name__, url_prefix="/unit_api")

# Register calibration session routes here to keep unit_api_bp ownership in this module.
register_calibration_session_routes(unit_api_bp)


for rule, options, view_func in registered_unit_api_routes():
    unit_api_bp.add_url_rule(rule, view_func=view_func, **options)


# Basic health check for workers exposing only unit_api
@unit_api_bp.route("/health", methods=["GET"])
def health_check() -> ResponseReturnValue:
    payload = {
        "status": "ok",
        "pioreactor_unit": HOSTNAME,
        "utc_time": current_utc_timestamp(),
    }
    return attach_cache_control(jsonify(payload), max_age=0)


@unit_api_bp.route("/hardware/check", methods=["POST", "PATCH"])
def check_hardware_for_model() -> DelayedResponseReturnValue:
    data = request.get_json(silent=True) or {}
    model_name = data.get("model_name")
    model_version = data.get("model_version")
    if not model_name or not model_version:
        abort_with(
            400,
            "Missing model_name or model_version",
            cause="Request JSON missing model_name or model_version.",
            remediation="Provide both model_name and model_version in the JSON payload.",
        )
    if (model_name, model_version) not in get_registered_models():
        abort_with(
            400,
            "Model name or version not found in available models.",
            cause=f"Unknown model '{model_name}' with version '{model_version}'.",
            remediation="Use a model_name and model_version from the registered models list.",
        )

    task = tasks.check_model_hardware(model_name, model_version)
    return create_task_response(task)


# Endpoint to check the status of a background task. unit_api is required to ping workers (who only expose unit_api)
@unit_api_bp.route("/task_results/<task_id>", methods=["GET"])
def get_task_status(task_id: str):
    blob = {"task_id": task_id, "result_url_path": "/unit_api/task_results/" + task_id}
    try:
        task = huey.result(task_id)
    except TaskLockedException:
        return (
            jsonify(
                blob
                | {
                    "status": "in_progress",
                    "error": "task is locked and already running.",
                    "error_info": {
                        "cause": "Another task with this ID is currently running.",
                        "remediation": "Wait for the task to finish, then retry.",
                    },
                }
            ),
            202,
        )
    except TaskException as e:
        # huey wraps the exception, so lets reraise it.
        return (
            jsonify(
                blob
                | {
                    "status": "failed",
                    "error": str(e),
                    "error_info": {
                        "cause": "Huey task failed with an exception.",
                        "remediation": "Check logs and retry.",
                    },
                }
            ),
            500,
        )

    if task is None:
        return jsonify(blob | {"status": "pending or not present"}), 202
    elif isinstance(task, Exception):
        return (
            jsonify(
                blob
                | {
                    "status": "failed",
                    "error": str(task),
                    "error_info": {
                        "cause": "Huey task failed with an exception.",
                        "remediation": "Check logs and retry.",
                    },
                }
            ),
            500,
        )
    else:
        return jsonify(blob | {"status": "complete", "result": task}), 200


def _format_protocol_text(value: str, device: str) -> str:
    if not value:
        return value
    device_label = device.replace("_", " ")
    return value.replace("{device}", device_label)


def _build_calibration_protocol_payloads() -> list[dict[str, Any]]:
    protocols: list[dict[str, Any]] = []
    for device, device_protocols in get_calibration_protocols_registry().items():
        for protocol_name, protocol in device_protocols.items():
            if not hasattr(protocol, "step_registry"):
                continue
            title = getattr(protocol, "title", "") or f"{protocol_name.replace('_', ' ').title()} calibration"
            description = getattr(protocol, "description", "")
            requirements = list(getattr(protocol, "requirements", ()))
            priority = int(protocol.priority)
            protocols.append(
                {
                    "id": f"{device}_{protocol_name}",
                    "target_device": device,
                    "protocol_name": protocol_name,
                    "priority": priority,
                    "title": _format_protocol_text(title, device),
                    "description": _format_protocol_text(description, device),
                    "requirements": [
                        _format_protocol_text(requirement, device) for requirement in requirements
                    ],
                }
            )
    return sorted(protocols, key=lambda item: (item["target_device"], item["priority"], item["title"]))


def require_leader(view_func):
    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        if HOSTNAME != get_leader_hostname():
            abort_with(403, "This endpoint is only available on the leader.")
        return view_func(*args, **kwargs)

    return _wrapped


def _task_is_locked(lock_name: str) -> bool:
    return huey.lock_task(lock_name).is_locked()


def _locked_task_response(lock_name: str) -> ResponseReturnValue:
    return jsonify({"status": "in_progress", "lock": lock_name}), 202


### SYSTEM


@unit_api_bp.route("/system/update/<target>", methods=["POST", "PATCH"])
def update_software_target(target: str) -> DelayedResponseReturnValue:
    if _task_is_locked("update-lock"):
        return _locked_task_response("update-lock")

    if target not in ("app",):  # todo: firmware
        abort_with(404, description="Invalid target")

    body = current_app.get_json(request.data, type=structs.ArgsOptionsEnvs)

    commands: tuple[str, ...] = tuple()
    commands += tuple(body.args)
    for option, value in body.options.items():
        commands += (f"--{option.replace('_', '-')}",)
        if value is not None:
            commands += (str(value),)

    if target == "app":
        task = tasks.pio_update_app(*commands)
    else:
        raise ValueError()

    return create_task_response(task)


@unit_api_bp.route("/system/update", methods=["POST", "PATCH"])
def update_software() -> DelayedResponseReturnValue:
    if _task_is_locked("update-lock"):
        return _locked_task_response("update-lock")

    body = current_app.get_json(request.data, type=structs.ArgsOptionsEnvs)

    commands: tuple[str, ...] = tuple()
    commands += tuple(body.args)
    for option, value in body.options.items():
        commands += (f"--{option.replace('_', '-')}",)
        if value is not None:
            commands += (str(value),)

    task = tasks.pio_update_app(*commands)
    return create_task_response(task)


@unit_api_bp.route("/system/reboot", methods=["POST", "PATCH"])
def reboot_system() -> DelayedResponseReturnValue:
    """Reboots unit"""
    # TODO: only let requests from the leader do this. Use lighttpd conf for this.
    if _task_is_locked("power-lock"):
        return _locked_task_response("power-lock")

    # don't reboot the leader right away, give time for any other posts/gets to occur.
    if HOSTNAME == get_leader_hostname():
        sleep(5)
    task = tasks.reboot()
    return create_task_response(task)


@unit_api_bp.route("/system/shutdown", methods=["POST", "PATCH"])
def shutdown_system() -> DelayedResponseReturnValue:
    """Shutdown unit"""
    if _task_is_locked("power-lock"):
        return _locked_task_response("power-lock")

    task = tasks.shutdown()
    return create_task_response(task)


@unit_api_bp.route("/system/web_server/status", methods=["GET"])
@require_leader
def get_web_server_status() -> ResponseReturnValue:
    services_to_check = ("lighttpd.service", "huey.service")

    if whoami.is_testing_env():
        status_text = "active"
        return attach_cache_control(
            jsonify(
                {
                    "service": ",".join(services_to_check),
                    "state": "ready",
                    "raw_status": status_text,
                }
            ),
            max_age=0,
        )

    raw_status_parts = []
    is_active = True
    for service in services_to_check:
        result = run(
            ["systemctl", "is-active", service],
            capture_output=True,
            text=True,
        )
        status_text = (result.stdout or result.stderr).strip()
        raw_status_parts.append(f"{service}={status_text}")
        is_active = is_active and (result.returncode == 0 and status_text == "active")

    status_text = ", ".join(raw_status_parts)
    state = "ready" if is_active else "disconnected"
    return attach_cache_control(
        jsonify(
            {
                "service": ",".join(services_to_check),
                "state": state,
                "raw_status": status_text,
            }
        ),
        max_age=3,
    )


@unit_api_bp.route("/system/web_server/restart", methods=["POST", "PATCH"])
@require_leader
def restart_web_server() -> DelayedResponseReturnValue:
    if _task_is_locked("web-restart-lock"):
        return _locked_task_response("web-restart-lock")

    task = tasks.restart_pioreactor_web_target()
    return create_task_response(task)


@unit_api_bp.route("/system/remove_file", methods=["POST", "PATCH"])
def remove_file() -> DelayedResponseReturnValue:
    task_name = "remove_file"
    disallow_file = Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_FILE_SYSTEM"
    if os.path.isfile(disallow_file):
        publish_to_error_log(f"Delete blocked because {disallow_file} is present", task_name)
        abort_with(
            403,
            "DISALLOW_UI_FILE_SYSTEM is present",
            cause="File system operations are disabled on this unit.",
            remediation="Remove DISALLOW_UI_FILE_SYSTEM or run the action locally via SSH.",
        )

    # use filepath in body
    body = current_app.get_json(request.data) or {}
    filepath = body.get("filepath")
    if not filepath:
        abort_with(
            400,
            "filepath field is required",
            cause="Request JSON missing 'filepath'.",
            remediation="Include a 'filepath' field in the JSON payload.",
        )
    assert filepath is not None

    base_dir = Path(os.environ["DOT_PIOREACTOR"]).resolve()
    candidate_path = Path(filepath).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = (base_dir / candidate_path).resolve()
    else:
        candidate_path = candidate_path.resolve()
    try:
        candidate_path.relative_to(base_dir)
    except ValueError:
        abort_with(
            403,
            "Access to this path is not allowed",
            cause="Requested path is outside the .pioreactor directory.",
            remediation="Provide a path within the .pioreactor directory.",
        )

    task = tasks.rm(str(candidate_path))
    return create_task_response(task)


# GET clock time
@unit_api_bp.route("/system/utc_clock", methods=["GET"])
def get_clock_time():
    try:
        current_time = current_utc_timestamp()
        return jsonify({"status": "success", "clock_time": current_time}), 200
    except Exception as e:
        abort_with(
            500,
            "Failed to read clock time",
            cause=str(e),
            remediation="Check system clock availability and server logs, then retry.",
        )


# PATCH / POST to set clock time
@unit_api_bp.route("/system/utc_clock", methods=["PATCH", "POST"])
def set_clock_time() -> DelayedResponseReturnValue:  # type: ignore[return]
    if _task_is_locked("clock-lock"):
        return _locked_task_response("clock-lock")

    if HOSTNAME == get_leader_hostname():
        data = request.get_json(silent=True)  # don't throw 415
        if not data:
            abort_with(
                400,
                "utc_clock_time field is required",
                cause="Request body is empty or not JSON.",
                remediation="Send JSON with a 'utc_clock_time' field.",
            )

        new_time = data.get("utc_clock_time")
        if not new_time:
            abort_with(
                400,
                "utc_clock_time field is required",
                cause="Missing 'utc_clock_time' value in JSON payload.",
                remediation="Provide an ISO 8601 timestamp in 'utc_clock_time'.",
            )

        # validate the timestamp
        try:
            to_datetime(new_time)
        except ValueError:
            abort_with(
                400,
                "Invalid utc_clock_time format. Use ISO 8601.",
                cause=f"Unable to parse '{new_time}' as ISO 8601.",
                remediation="Use an ISO 8601 timestamp, e.g. 2025-01-31T12:34:56Z.",
            )

        # Update the system clock (requires admin privileges)
        t = tasks.update_clock(new_time)
        return create_task_response(t)
    else:
        # sync using chrony
        t = tasks.sync_clock()
        return create_task_response(t)


#### DIR
@unit_api_bp.route("/system/path/", defaults={"req_path": ""})
@unit_api_bp.route("/system/path/<path:req_path>")
def list_system_path(req_path: str):
    if os.path.isfile(Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_FILE_SYSTEM"):
        abort_with(
            403,
            "DISALLOW_UI_FILE_SYSTEM is present",
            cause="File system browsing is disabled on this unit.",
            remediation="Remove DISALLOW_UI_FILE_SYSTEM or browse locally via SSH.",
        )

    BASE_DIR = os.environ["DOT_PIOREACTOR"]

    # Safely join to prevent directory traversal
    safe_path = safe_join(BASE_DIR, req_path)
    if not safe_path:
        abort_with(
            403,
            "Invalid path.",
            cause="Requested path could not be safely resolved.",
            remediation="Provide a path within the .pioreactor directory.",
        )

    # Check if the path actually exists
    if not os.path.exists(safe_path):
        abort_with(
            404,
            "Path not found.",
            cause=f"Path does not exist: {req_path}",
            remediation="Check the path and try again.",
        )

    # If it's a file, serve the file
    if os.path.isfile(safe_path):
        if safe_path.endswith((".sqlite", ".sqlite.backup", ".sqlite-shm", ".sqlite-wal")):
            abort_with(
                403,
                "Access to downloading sqlite files is restricted.",
                cause="SQLite files are blocked from download via the API.",
                remediation="Access the database directly on the device.",
            )

        return send_file(safe_path, mimetype="text/plain")

    # Joining the base and the requested path
    abs_path = os.path.join(BASE_DIR, req_path)

    # Return 404 if path doesn't exist
    if not os.path.exists(abs_path):
        abort_with(
            404,
            "Path not found.",
            cause=f"Path does not exist: {req_path}",
            remediation="Check the path and try again.",
        )

    # Check if path is a file and serve
    if os.path.isfile(abs_path):
        return send_file(abs_path)

    # Show directory contents
    current, dirs, files = next(os.walk(abs_path))

    return attach_cache_control(
        jsonify(
            {
                "current": current,
                "dirs": sorted([d for d in dirs if not d == "__pycache__"]),
                "files": sorted(files),
            }
        )
    )


## RUNNING JOBS CONTROL


@unit_api_bp.route("/jobs/run/job_name/<job_name>", methods=["PATCH", "POST"])
def run_job(job_name: str) -> DelayedResponseReturnValue:
    """
    Body should look like (all optional)
    {
      "options": {
        "option1": "value1",
        "option2": "value2"
      },
      "env": {
        "EXPERIMENT": "test",
        "JOB_SOURCE": "user",
      }
      "args": ["arg1", "arg2"],
      "config_overrides": [ ["stirring.config" ,"pwm_hz", "100"], ]
    }
    Ex:

    curl -X POST http://worker.local/unit_api/jobs/run/job_name/stirring -H "Content-Type: application/json" -d '{
      "options": {},
      "args": []
    }'
    """
    if is_rate_limited(job_name):
        abort_with(429, "Too many requests, please try again later.")

    json = current_app.get_json(request.data, type=structs.ArgsOptionsEnvsConfigOverrides)
    args = json.args
    options = json.options
    env = json.env | {
        "TESTING": str(int(whoami.is_testing_env())),
    }
    config_overrides = json.config_overrides

    config_overrides_as_flags: tuple[str, ...] = sum(
        [("--config-override",) + tuple(_args) for _args in config_overrides], tuple()
    )

    commands: tuple[str, ...] = (job_name,)
    commands += tuple(args)
    for option, value in options.items():
        commands += (f"--{option.replace('_', '-')}",)
        if value is not None:
            commands += (str(value),)

    task = tasks.pio_run(*commands, env=env, config_overrides=config_overrides_as_flags)
    return create_task_response(task)


@unit_api_bp.route("/jobs/stop/all", methods=["PATCH", "POST"])
def stop_all_jobs() -> DelayedResponseReturnValue:
    task = tasks.kill_jobs_task(all_jobs=True)
    return create_task_response(task)


@unit_api_bp.route("/jobs/stop", methods=["PATCH", "POST"])
def stop_jobs() -> DelayedResponseReturnValue:
    if not request.data:
        return abort_with(400, "No job filter specified")
    json = current_app.get_json(request.data)

    job_name = json.get("job_name")
    experiment = json.get("experiment")
    job_source = json.get("job_source")
    job_id = json.get("job_id")
    if not any([job_name, experiment, job_source, job_id]):
        return abort_with(400, "No job filter specified")

    task = tasks.kill_jobs_task(
        job_name=job_name,
        experiment=experiment,
        job_source=job_source,
        job_id=job_id,
    )
    return create_task_response(task)


@unit_api_bp.route("/jobs/running/experiments/<experiment>", methods=["GET"])
def get_running_jobs_for_experiment(experiment: str) -> ResponseReturnValue:
    jobs = query_temp_local_metadata_db(
        """SELECT * FROM pio_job_metadata where is_running=1 and experiment = (?)""",
        (experiment,),
    )

    return jsonify(jobs)


@unit_api_bp.route("/jobs/running", methods=["GET"])
def get_all_running_jobs() -> ResponseReturnValue:
    jobs = query_temp_local_metadata_db("SELECT * FROM pio_job_metadata where is_running=1")

    return jsonify(jobs)


@unit_api_bp.route("/jobs/running/<job_name>", methods=["GET"])
def get_running_job(job_name: str) -> ResponseReturnValue:
    jobs = query_temp_local_metadata_db(
        "SELECT * FROM pio_job_metadata where is_running=1 and job_name=?", (job_name,)
    )
    return jsonify(jobs)


@unit_api_bp.route("/long_running_jobs/running", methods=["GET"])
def get_all_long_running_jobs() -> ResponseReturnValue:
    jobs = query_temp_local_metadata_db(
        "SELECT * FROM pio_job_metadata where is_running=1 and is_long_running_job=1"
    )
    return jsonify(jobs)


### SETTINGS


@unit_api_bp.route("/jobs/settings/job_name/<job_name>", methods=["GET"])
def get_job_settings(job_name: str) -> ResponseReturnValue:
    """
    {
      "settings": {
        <setting1>: <value1>,
        <setting2>: <value2>
      }
    }
    """
    settings = query_temp_local_metadata_db(
        """
    SELECT s.setting, s.value FROM
        pio_job_published_settings s
        JOIN pio_job_metadata m
            on m.job_id = s.job_id
        WHERE m.is_running=1 AND m.job_name=(?);
    """,
        (job_name,),
    )
    assert isinstance(settings, list)
    if settings:
        return jsonify({"settings": {s["setting"]: s["value"] for s in settings}})
    else:
        abort_with(404, "No settings found for job.")


@unit_api_bp.route("/jobs/settings/job_name/<job_name>/setting/<setting>", methods=["GET"])
def get_job_setting(job_name: str, setting: str) -> ResponseReturnValue:
    setting_metadata = query_temp_local_metadata_db(
        """
    SELECT s.setting, s.value FROM
        pio_job_published_settings s
        JOIN pio_job_metadata m
            on m.job_id = s.job_id
        WHERE m.is_running=1 AND m.job_name=(?) AND setting = (?)
    """,
        (job_name, setting),
        one=True,
    )
    assert isinstance(setting_metadata, (dict, type(None)))
    if setting_metadata:
        return jsonify({setting_metadata["setting"]: setting_metadata["value"]})
    else:
        abort_with(404, "Setting not found.")


@unit_api_bp.route("/jobs/settings/job_name/<job_name>", methods=["PATCH"])
def update_job(job_name: str) -> ResponseReturnValue:
    """
    The body should look like:

    {
      "settings": {
        <setting1>: <value1>,
        <setting2>: <value2>
      },
    }
    """
    # body = request.get_json()
    abort_with(503, "Not implemented.")


@unit_api_bp.route("/capabilities", methods=["GET"])
def get_capabilities() -> ResponseReturnValue:
    from pioreactor.utils.capabilities import collect_capabilities

    return jsonify(collect_capabilities())


### PLUGINS

PLUGIN_ALLOWLIST_FILENAME = "plugins/api_plugins_allowlist.json"


def _canonicalize_package_name(raw: str) -> str:
    # normalize to something close to pip's canonical form for comparison
    name = raw.strip()
    for sep in ("[", "==", ">=", "<=", "~=", "!=", ">", "<"):
        if sep in name:
            name = name.split(sep, 1)[0]
    return name.replace("_", "-").lower()


def _load_plugin_allowlist() -> set[str]:
    allowlist_path = Path(os.environ["DOT_PIOREACTOR"]) / PLUGIN_ALLOWLIST_FILENAME
    try:
        contents = current_app.get_json(allowlist_path.read_bytes())
    except Exception as e:
        publish_to_error_log(f"{PLUGIN_ALLOWLIST_FILENAME} is not present or invalid JSON: {e}", "plugins")
        return set()
    return {_canonicalize_package_name(c["name"]) for c in contents}


@unit_api_bp.route("/plugins/installed", methods=["GET"])
def get_installed_plugins() -> ResponseReturnValue:
    result = tasks.list_plugins_installed()
    try:
        status, msg = result(blocking=True, timeout=10)
    except HueyException:
        status, msg = False, "Timed out."

    if not status:
        abort_with(404, msg)
    else:
        # sometimes an error from a plugin will be printed. We just want to last line, the json bit.
        _, _, plugins_as_json = msg.rpartition("\n")
        return attach_cache_control(
            Response(
                response=plugins_as_json,
                status=200,
                mimetype="application/json",
            )
        )


@unit_api_bp.route("/plugins/installed/<filename>", methods=["GET"])
def get_installed_plugin(filename: str) -> ResponseReturnValue:
    """get a specific Python file in the .pioreactor/plugin folder"""
    # security bit: strip out any paths that may be attached, ex: ../../../root/bad
    file = Path(filename).name

    try:
        if Path(file).suffix != ".py":
            raise IOError("must provide a .py file")

        specific_plugin_path = Path(os.environ["DOT_PIOREACTOR"]) / "plugins" / file
        return attach_cache_control(
            Response(
                response=specific_plugin_path.read_text(),
                status=200,
                mimetype="text/plain",
            )
        )
    except IOError:
        abort_with(
            404,
            "must provide a .py file",
            cause="Requested plugin filename is not a .py file.",
            remediation="Request a specific plugin file ending with .py.",
        )
    except Exception:
        abort_with(
            500,
            "server error",
            cause="Failed to load the requested plugin file.",
            remediation="Check file permissions and server logs.",
        )


@unit_api_bp.route("/plugins/install", methods=["POST", "PATCH"])
def install_plugin() -> DelayedResponseReturnValue:
    """
    runs `pio plugin install ....`
    Body should look like:
    {
      "options": {
        "option1": "value1",
        "option2": "value2"
      },
      "args": ["arg1", "arg2"]
    }

    Ex:
    {
      "options": {
        "source": "pathtofile",
      },
      "args": ["my_plugin_name"]
    }

    """

    # there is a security problem here. See https://github.com/Pioreactor/pioreactor/issues/421
    if os.path.isfile(Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_INSTALLS"):
        abort_with(
            403,
            "DISALLOW_UI_INSTALLS is present",
            cause="Plugin installs are disabled on this unit.",
            remediation="Remove DISALLOW_UI_INSTALLS or install via SSH.",
        )

    # allowlist = _load_plugin_allowlist()
    # if not allowlist:
    #    abort_with(
    #        403,
    #        "Plugin installs via API are disabled: plugins_allowlist.json missing, empty, or invalid.",
    #    )

    body = current_app.get_json(request.data, type=structs.ArgsOptionsEnvs)

    if not body.args:
        abort_with(
            400,
            "Plugin name is required",
            cause="No plugin name provided in args.",
            remediation="Provide a single plugin name in args.",
        )
    if len(body.args) > 1:
        abort_with(
            400,
            "Install one plugin at a time via the API",
            cause=f"Received {len(body.args)} plugin arguments.",
            remediation="Provide exactly one plugin name in args.",
        )

    # requested_plugin = _canonicalize_package_name(body.args[0])
    # if requested_plugin not in allowlist:
    #    abort_with(
    #        403,
    #        f"Plugin '{requested_plugin}' is not in the allowlist for API installs.",
    #    )

    source = body.options.get("source")
    task = tasks.install_plugin_task(body.args[0], source=source)
    return create_task_response(task)


@unit_api_bp.route("/plugins/uninstall", methods=["POST", "PATCH"])
def uninstall_plugin() -> DelayedResponseReturnValue:
    """
    Body should look like:
    {
      "options": {
        "option1": "value1",
        "option2": "value2"
      },
      "args": ["arg1", "arg2"]
    }
    """
    body = current_app.get_json(request.data, type=structs.ArgsOptionsEnvs)

    if len(body.args) != 1:
        abort_with(
            400,
            "Uninstall one plugin at a time via the API",
            cause=f"Received {len(body.args)} plugin arguments.",
            remediation="Provide exactly one plugin name in args.",
        )

    task = tasks.uninstall_plugin_task(body.args[0])
    return create_task_response(task)


### VERSIONS


@unit_api_bp.route("/versions/app", methods=["GET"])
def get_app_version() -> ResponseReturnValue:
    return attach_cache_control(jsonify({"version": __version__}), max_age=10000)


### CALIBRATIONS


@unit_api_bp.route("/calibration_protocols", methods=["GET"])
def get_calibration_protocols() -> ResponseReturnValue:
    return attach_cache_control(jsonify(_build_calibration_protocol_payloads()), max_age=10)


@unit_api_bp.route("/calibrations/<device>", methods=["POST"])
def create_calibration(device: str) -> ResponseReturnValue:
    """
    Create a new calibration for the specified device.
    """
    # calibration_dir = CALIBRATION_PATH / device
    # if folder does not exist, users should make it with mkdir -p ... && chown -R pioreactor:www-data ...

    try:
        raw_yaml = request.get_json()["calibration_data"]
        calibration_data = yaml_decode(raw_yaml, type=AllCalibrations)
        calibration_name = calibration_data.calibration_name

        if not calibration_name or not is_valid_unix_filename(calibration_name):
            abort_with(
                400,
                description="Missing or invalid 'calibration_name'.",
                cause="Calibration name missing or contains invalid characters.",
                remediation="Provide a valid calibration_name using letters, digits, dashes, or underscores.",
            )
        elif not device or not is_valid_unix_filename(device):
            abort_with(
                400,
                description="Missing or invalid 'device'.",
                cause="Device name missing or contains invalid characters.",
                remediation="Provide a valid device name (letters, digits, dashes, or underscores).",
            )

        path = calibration_data.path_on_disk_for_device(device)
        tasks.save_file(path, raw_yaml)

        # Respond with success and the created calibration details
        return jsonify({"msg": "Calibration created successfully.", "path": str(path)}), 201

    except Exception as e:
        publish_to_error_log(f"Error creating calibration: {e}", "create_calibration")
        abort_with(
            500,
            description="Failed to create calibration.",
            cause="Unable to save calibration file.",
            remediation="Check file permissions and server logs.",
        )


@unit_api_bp.route("/calibrations/<device>/<calibration_name>", methods=["DELETE"])
def delete_calibration(device: str, calibration_name: str) -> ResponseReturnValue:
    """
    Delete a specific calibration for a given device.
    """
    calibration_path = CALIBRATION_PATH / device / f"{calibration_name}.yaml"

    if not calibration_path.exists():
        abort_with(
            404,
            description=f"Calibration '{calibration_name}' not found for device '{device}'.",
            cause="Calibration file is missing from disk.",
            remediation="List available calibrations for this device and retry.",
        )

    try:
        calibration_path.unlink()
        with local_persistent_storage("active_calibrations") as cache:
            if cache.get(device) == calibration_name:
                cache.pop(device)

        return (
            jsonify({"msg": f"Calibration '{calibration_name}' for device '{device}' deleted successfully."}),
            200,
        )

    except Exception as e:
        publish_to_error_log(f"Error deleting calibration: {e}", "delete_calibration")
        abort_with(
            500,
            description="Failed to delete calibration.",
            cause="Unable to delete calibration file.",
            remediation="Check file permissions and server logs.",
        )


@unit_api_bp.route("/calibrations", methods=["GET"])
def get_all_calibrations() -> ResponseReturnValue:
    calibration_dir = CALIBRATION_PATH

    if not calibration_dir.exists():
        abort_with(
            404,
            "Calibration directory does not exist.",
            cause="Calibration storage directory is missing on disk.",
            remediation="Create the calibration directory or restore from backup.",
        )

    all_calibrations: dict[str, list] = {}

    with local_persistent_storage("active_calibrations") as cache:
        for file in sorted(calibration_dir.glob("*/*.yaml")):
            try:
                device = file.parent.name
                cal = to_builtins(yaml_decode(file.read_bytes(), type=AllCalibrations))
                cal["is_active"] = cache.get(device) == cal["calibration_name"]
                cal["pioreactor_unit"] = HOSTNAME
                if device in all_calibrations:
                    all_calibrations[device].append(cal)
                else:
                    all_calibrations[device] = [cal]
            except Exception as e:
                publish_to_error_log(f"Error reading {file.stem}: {e}", "get_all_calibrations")

    return attach_cache_control(jsonify(all_calibrations), max_age=10)


@unit_api_bp.route("/active_calibrations", methods=["GET"])
def get_all_active_calibrations() -> ResponseReturnValue:
    calibration_dir = CALIBRATION_PATH

    if not calibration_dir.exists():
        abort_with(
            404,
            "Calibration directory does not exist.",
            cause="Calibration storage directory is missing on disk.",
            remediation="Create the calibration directory or restore from backup.",
        )

    all_calibrations: dict[str, dict] = {}

    with local_persistent_storage("active_calibrations") as cache:
        for device in cache.iterkeys():
            cal_name = cache[device]
            cal_file_path = calibration_dir / device / f"{cal_name}.yaml"
            try:
                cal = to_builtins(yaml_decode(cal_file_path.read_bytes(), type=AllCalibrations))
                cal["is_active"] = True
                cal["pioreactor_unit"] = HOSTNAME
                all_calibrations[device] = cal
            except Exception as e:
                publish_to_error_log(
                    f"Error reading {cal_file_path.stem}: {e}", "get_all_active_calibrations"
                )

    return attach_cache_control(jsonify(all_calibrations), max_age=10)


@unit_api_bp.route("/active_estimators", methods=["GET"])
def get_all_active_estimators() -> ResponseReturnValue:
    estimator_dir = ESTIMATOR_PATH

    if not estimator_dir.exists():
        return attach_cache_control(jsonify({}), max_age=10)

    all_estimators: dict[str, dict] = {}

    with local_persistent_storage("active_estimators") as cache:
        for device in cache.iterkeys():
            estimator_name = cache[device]
            estimator_file_path = estimator_dir / device / f"{estimator_name}.yaml"
            if not estimator_file_path.exists():
                continue
            try:
                estimator = to_builtins(yaml_decode(estimator_file_path.read_bytes(), type=AllEstimators))
                estimator["is_active"] = True
                estimator["pioreactor_unit"] = HOSTNAME
                all_estimators[device] = estimator
            except Exception as e:
                publish_to_error_log(
                    f"Error reading {estimator_file_path.stem}: {e}", "get_all_active_estimators"
                )

    return attach_cache_control(jsonify(all_estimators), max_age=10)


@unit_api_bp.route("/estimators", methods=["GET"])
def get_all_estimators() -> ResponseReturnValue:
    estimator_dir = ESTIMATOR_PATH

    if not estimator_dir.exists():
        return attach_cache_control(jsonify({}), max_age=10)

    all_estimators: dict[str, list] = {}

    with local_persistent_storage("active_estimators") as cache:
        for file in sorted(estimator_dir.glob("*/*.yaml")):
            try:
                device = file.parent.name
                estimator = to_builtins(yaml_decode(file.read_bytes(), type=AllEstimators))
                estimator["is_active"] = cache.get(device) == estimator.get("estimator_name")
                estimator["pioreactor_unit"] = HOSTNAME
                estimator["device"] = device
                if device in all_estimators:
                    all_estimators[device].append(estimator)
                else:
                    all_estimators[device] = [estimator]
            except Exception as e:
                publish_to_error_log(f"Error reading {file.stem}: {e}", "get_all_estimators")

    return attach_cache_control(jsonify(all_estimators), max_age=10)


@unit_api_bp.route("/zipped_calibrations", methods=["GET"])
def get_zipped_calibrations() -> ResponseReturnValue:
    calibration_dir = CALIBRATION_PATH

    if not calibration_dir.exists():
        abort_with(
            404,
            "Calibration directory does not exist.",
            cause="Calibration storage directory is missing on disk.",
            remediation="Create the calibration directory or restore from backup.",
        )

    buffer = BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in sorted(calibration_dir.rglob("*.yaml")):
            if file_path.is_file():
                arc_name = file_path.relative_to(calibration_dir)
                zip_file.write(str(file_path), arcname=str(arc_name))

    # Move the cursor to the beginning of the buffer
    buffer.seek(0)

    # Return the file using send_file
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{HOSTNAME}_calibrations.zip",  # Name shown to the user
        mimetype="application/zip",
    )


@unit_api_bp.route("/zipped_dot_pioreactor", methods=["GET"])
def get_zipped_dot_pioreactor() -> ResponseReturnValue:
    """Create and return a ZIP of the entire DOT_PIOREACTOR directory.

    Notes:
    - Respects DISALLOW_UI_FILE_SYSTEM flag for parity with directory browsing.
    - Uses a temp file on disk to avoid holding large zips in memory.
    - Zips all contents recursively with paths relative to DOT_PIOREACTOR.
    """
    if (Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_FILE_SYSTEM").is_file():
        abort_with(
            403,
            "DISALLOW_UI_FILE_SYSTEM is present",
            cause="File system access is disabled on this unit.",
            remediation="Remove DISALLOW_UI_FILE_SYSTEM or export files locally via SSH.",
        )

    base_dir = Path(os.environ["DOT_PIOREACTOR"]).resolve()

    tmp = NamedTemporaryFile(prefix=f"{HOSTNAME}_dot_pioreactor_", suffix=".zip", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()  # will write to this path below

    exported_at = current_utc_timestamp()
    leader_hostname = ""
    try:
        leader_hostname = get_leader_hostname()
    except Exception:
        # avoid failing the export if the leader hostname can't be resolved
        leader_hostname = "unknown"

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            skip_backup = base_dir / "storage" / "pioreactor.sqlite.backup"
            for path in sorted(base_dir.rglob("*")):
                if not path.exists():
                    continue
                if path == skip_backup:
                    continue
                # Store paths inside the archive relative to DOT_PIOREACTOR
                arcname = path.relative_to(base_dir)
                try:
                    zf.write(str(path), arcname=str(arcname))
                except Exception as e:
                    publish_to_error_log(f"Failed to add {path} to zip: {e}", "zipped_dot_pioreactor")

            metadata = {
                "metadata_version": 1,
                "name": HOSTNAME,
                "leader_hostname": leader_hostname,
                "is_leader": HOSTNAME == leader_hostname,
                "app_version": __version__,
                "exported_at_utc": exported_at,
            }
            zf.writestr("pioreactor_export_metadata.json", json.dumps(metadata))

        @after_this_request
        def cleanup_temp_file(response: Response) -> Response:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return response

        return send_file(
            str(tmp_path),
            as_attachment=True,
            download_name=f"{HOSTNAME}_dot_pioreactor.zip",
            mimetype="application/zip",
        )
    finally:
        pass


@unit_api_bp.route("/import_zipped_dot_pioreactor", methods=["POST"])
def import_dot_pioreactor_from_zip() -> ResponseReturnValue:
    task_name = "import_zipped_dot_pioreactor"
    publish_to_log("Starting import of zipped DOT_PIOREACTOR archive", task_name, "INFO")

    if whoami.is_testing_env():
        return Response(status=202)

    disallow_file = Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_FILE_SYSTEM"
    if disallow_file.is_file():
        publish_to_error_log(f"Import blocked because {disallow_file} is present", task_name)
        abort_with(
            403,
            "DISALLOW_UI_FILE_SYSTEM is present",
            cause="File system operations are disabled on this unit.",
            remediation="Remove DISALLOW_UI_FILE_SYSTEM or run the import locally via SSH.",
        )

    if _task_is_locked("import-dot-pioreactor-lock"):
        return _locked_task_response("import-dot-pioreactor-lock")

    uploaded = request.files.get("archive")
    if uploaded is None or uploaded.filename == "":
        publish_to_error_log("No archive uploaded in import request", task_name)
        abort_with(
            400,
            "No archive uploaded",
            cause="Missing 'archive' file in multipart form-data.",
            remediation="Upload a zip file using the 'archive' field.",
        )

    tmp = NamedTemporaryFile(prefix="import_dot_pioreactor_", suffix=".zip", delete=False)
    tmp_path = Path(tmp.name)
    publish_to_log(f"Saving uploaded archive to temporary file {tmp_path}", task_name, "DEBUG")
    uploaded.save(tmp_path)
    tmp.close()
    try:
        tmp_path.chmod(0o640)
    except OSError as exc:
        publish_to_error_log(f"Failed to set permissions on {tmp_path}: {exc}", task_name)

    try:
        metadata = tasks.validate_dot_pioreactor_archive(tmp_path, HOSTNAME)
    except ValueError as exc:
        publish_to_error_log(f"Zip validation failed: {exc}", task_name)
        tmp_path.unlink(missing_ok=True)
        abort_with(
            400,
            str(exc),
            cause="Zip archive failed validation.",
            remediation="Ensure the archive is a valid Pioreactor export and retry.",
        )
    except zipfile.BadZipFile:
        publish_to_error_log("Uploaded file is not a valid zip archive", task_name)
        tmp_path.unlink(missing_ok=True)
        abort_with(
            400,
            "Uploaded file is not a valid zip archive",
            cause="Archive could not be read as a zip file.",
            remediation="Upload a valid .zip file.",
        )
    except Exception as exc:
        publish_to_error_log(f"Failed to inspect uploaded archive: {exc}", task_name)
        tmp_path.unlink(missing_ok=True)
        abort_with(
            500,
            "Failed to inspect uploaded archive",
            cause="Unexpected error while inspecting the uploaded archive.",
            remediation="Check server logs and retry with a fresh export.",
        )

    if metadata is None:
        publish_to_log(
            "Archive missing metadata file, assuming legacy export without host validation",
            task_name,
            "DEBUG",
        )
    else:
        exported_name = metadata.get("name")
        publish_to_log(
            f"Loaded archive metadata for unit {exported_name or 'unknown'}",
            task_name,
            "DEBUG",
        )

    base_dir = Path(os.environ["DOT_PIOREACTOR"]).resolve()
    publish_to_log(f"Resolved DOT_PIOREACTOR base directory to {base_dir}", task_name, "DEBUG")

    try:
        task = tasks.import_dot_pioreactor_archive(str(tmp_path))
    except HueyException as exc:
        publish_to_error_log(f"Failed to enqueue import task: {exc}", task_name)
        tmp_path.unlink(missing_ok=True)
        abort_with(
            500,
            "Failed to enqueue import task",
            cause="Huey queue rejected the import task.",
            remediation="Check Huey worker status and retry.",
        )
    except Exception as exc:  # pragma: no cover - unexpected failure
        publish_to_error_log(f"Failed to enqueue import task: {exc}", task_name)
        tmp_path.unlink(missing_ok=True)
        abort_with(
            500,
            "Failed to enqueue import task",
            cause="Unexpected error while enqueueing the import task.",
            remediation="Check server logs and retry.",
        )

    publish_to_log("Import task submitted to Huey", task_name, "DEBUG")
    return create_task_response(task)


@unit_api_bp.route("/calibrations/<device>", methods=["GET"])
def get_calibrations_by_device(device: str) -> ResponseReturnValue:
    calibration_dir = CALIBRATION_PATH / device

    if not calibration_dir.exists():
        abort_with(
            404,
            "Calibration directory does not exist.",
            cause="Calibration storage directory is missing on disk.",
            remediation="Create the calibration directory or restore from backup.",
        )

    calibrations: list[dict] = []

    with local_persistent_storage("active_calibrations") as c:
        for file in sorted(calibration_dir.glob("*.yaml")):
            try:
                cal = to_builtins(yaml_decode(file.read_bytes(), type=AllCalibrations))
                cal["is_active"] = c.get(device) == cal["calibration_name"]
                cal["pioreactor_unit"] = HOSTNAME
                calibrations.append(cal)
            except Exception as e:
                publish_to_error_log(f"Error reading {file.stem}: {e}", "get_calibrations_by_device")

    return attach_cache_control(jsonify(calibrations), max_age=10)


@unit_api_bp.route("/calibrations/<device>/<calibration_name>", methods=["GET"])
def get_calibration(device: str, calibration_name: str) -> ResponseReturnValue:
    calibration_path = CALIBRATION_PATH / device / f"{calibration_name}.yaml"

    if not calibration_path.exists():
        abort_with(
            404,
            "Calibration file does not exist.",
            cause=f"Calibration '{calibration_name}' missing for device '{device}'.",
            remediation="List available calibrations for the device and retry.",
        )

    with local_persistent_storage("active_calibrations") as c:
        try:
            cal = to_builtins(yaml_decode(calibration_path.read_bytes(), type=AllCalibrations))
            cal["is_active"] = c.get(device) == cal["calibration_name"]
            cal["pioreactor_unit"] = HOSTNAME
            return attach_cache_control(jsonify(cal), max_age=10)
        except Exception as e:
            publish_to_error_log(f"Error reading {calibration_path.stem}: {e}", "get_calibration")
            abort_with(
                500,
                "Failed to read calibration file.",
                cause="Unable to parse calibration YAML.",
                remediation="Check calibration file contents or re-upload the calibration.",
            )


@unit_api_bp.route("/estimators/<device>", methods=["GET"])
def get_estimators_by_device(device: str) -> ResponseReturnValue:
    estimator_dir = ESTIMATOR_PATH / device

    if not estimator_dir.exists():
        return attach_cache_control(jsonify([]), max_age=10)

    estimators: list[dict] = []
    with local_persistent_storage("active_estimators") as c:
        for file in sorted(estimator_dir.glob("*.yaml")):
            try:
                estimator = to_builtins(yaml_decode(file.read_bytes(), type=AllEstimators))
                estimator["is_active"] = c.get(device) == estimator.get("estimator_name")
                estimator["pioreactor_unit"] = HOSTNAME
                estimator["device"] = device
                estimators.append(estimator)
            except Exception as e:
                publish_to_error_log(f"Error reading {file.stem}: {e}", "get_estimators_by_device")

    return attach_cache_control(jsonify(estimators), max_age=10)


@unit_api_bp.route("/estimators/<device>/<estimator_name>", methods=["GET"])
def get_estimator(device: str, estimator_name: str) -> ResponseReturnValue:
    estimator_path = ESTIMATOR_PATH / device / f"{estimator_name}.yaml"

    if not estimator_path.exists():
        abort_with(
            404,
            description=f"Estimator '{estimator_name}' not found for device '{device}'.",
            cause="Estimator file is missing from disk.",
            remediation="List available estimators for this device and retry.",
        )

    with local_persistent_storage("active_estimators") as c:
        try:
            estimator = to_builtins(yaml_decode(estimator_path.read_bytes(), type=AllEstimators))
            estimator["is_active"] = c.get(device) == estimator.get("estimator_name")
            estimator["pioreactor_unit"] = HOSTNAME
            estimator["device"] = device
            return attach_cache_control(jsonify(estimator), max_age=10)
        except Exception as e:
            publish_to_error_log(f"Error reading {estimator_path.stem}: {e}", "get_estimator")
            abort_with(
                500,
                "Failed to read estimator file.",
                cause="Unable to parse estimator YAML.",
                remediation="Check estimator file contents or re-upload the estimator.",
            )


@unit_api_bp.route("/active_calibrations/<device>/<calibration_name>", methods=["PATCH"])
def set_active_calibration(device: str, calibration_name: str) -> ResponseReturnValue:
    with local_persistent_storage("active_calibrations") as c:
        c[device] = calibration_name

    return {"status": "success"}, 200


@unit_api_bp.route("/active_calibrations/<device>", methods=["DELETE"])
def remove_active_status_calibration(device: str) -> ResponseReturnValue:
    with local_persistent_storage("active_calibrations") as c:
        if device in c:
            c.pop(device)

    return {"status": "success"}, 200


@unit_api_bp.route("/active_estimators/<device>/<estimator_name>", methods=["PATCH"])
def set_active_estimator(device: str, estimator_name: str) -> ResponseReturnValue:
    with local_persistent_storage("active_estimators") as c:
        c[device] = estimator_name

    return {"status": "success"}, 200


@unit_api_bp.route("/active_estimators/<device>", methods=["DELETE"])
def remove_active_status_estimator(device: str) -> ResponseReturnValue:
    with local_persistent_storage("active_estimators") as c:
        if device in c:
            c.pop(device)

    return {"status": "success"}, 200


@unit_api_bp.route("/estimators/<device>/<estimator_name>", methods=["DELETE"])
def delete_estimator(device: str, estimator_name: str) -> ResponseReturnValue:
    estimator_path = ESTIMATOR_PATH / device / f"{estimator_name}.yaml"

    if not estimator_path.exists():
        abort_with(
            404,
            description=f"Estimator '{estimator_name}' not found for device '{device}'.",
            cause="Estimator file is missing from disk.",
            remediation="List available estimators for this device and retry.",
        )

    try:
        estimator_path.unlink()
        with local_persistent_storage("active_estimators") as cache:
            if cache.get(device) == estimator_name:
                cache.pop(device)

        return (
            jsonify({"msg": f"Estimator '{estimator_name}' for device '{device}' deleted successfully."}),
            200,
        )
    except Exception as e:
        publish_to_error_log(f"Error deleting estimator: {e}", "delete_estimator")
        abort_with(
            500,
            description="Failed to delete estimator.",
            cause="Unable to delete estimator file.",
            remediation="Check file permissions and server logs.",
        )
