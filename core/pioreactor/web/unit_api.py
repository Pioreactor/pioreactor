# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import zipfile
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep

from flask import abort
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
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.calibrations.protocols.od_reference_standard import advance_reference_standard_session
from pioreactor.calibrations.protocols.od_reference_standard import get_reference_standard_step
from pioreactor.calibrations.protocols.od_reference_standard import start_reference_standard_session
from pioreactor.calibrations.protocols.od_standards import advance_standards_session
from pioreactor.calibrations.protocols.od_standards import get_standards_step
from pioreactor.calibrations.protocols.od_standards import start_standards_session
from pioreactor.calibrations.protocols.pump_duration_based import advance_duration_based_session
from pioreactor.calibrations.protocols.pump_duration_based import get_duration_based_step
from pioreactor.calibrations.protocols.pump_duration_based import start_duration_based_session
from pioreactor.calibrations.protocols.stirring_dc_based import advance_dc_based_session
from pioreactor.calibrations.protocols.stirring_dc_based import get_dc_based_step
from pioreactor.calibrations.protocols.stirring_dc_based import start_dc_based_session
from pioreactor.calibrations.structured_session import abort_calibration_session
from pioreactor.calibrations.structured_session import load_calibration_session
from pioreactor.calibrations.structured_session import save_calibration_session
from pioreactor.config import get_leader_hostname
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
from pioreactor.web.utils import attach_cache_control
from pioreactor.web.utils import create_task_response
from pioreactor.web.utils import DelayedResponseReturnValue
from pioreactor.web.utils import is_rate_limited
from pioreactor.web.utils import is_valid_unix_filename
from werkzeug.utils import safe_join


AllCalibrations = subclass_union(CalibrationBase)

unit_api_bp = Blueprint("unit_api", __name__, url_prefix="/unit_api")


def _execute_calibration_action(action: str, payload: dict[str, object]) -> dict[str, object]:
    def _raise_if_task_failed(result: object, message: str) -> None:
        if isinstance(result, Exception):
            raise ValueError(message)

    if action == "pump":
        task = tasks.calibration_execute_pump(
            str(payload["pump_device"]),
            float(payload["duration_s"]),
            float(payload["hz"]),
            float(payload["dc"]),
        )
        try:
            success = task(blocking=True, timeout=30)
        except HueyException as exc:
            raise ValueError("Pump action timed out.") from exc
        _raise_if_task_failed(success, "Pump action failed.")
        if not success:
            raise ValueError("Pump action failed.")
        return {}

    if action == "od_standards_measure":
        task = tasks.calibration_measure_standard(
            float(payload["rpm"]),
            payload["channel_angle_map"],
        )
        try:
            voltages = task(blocking=True, timeout=30)
        except HueyException as exc:
            raise ValueError("OD measurement timed out.") from exc
        _raise_if_task_failed(voltages, "OD measurement failed.")
        return {"voltages": voltages}

    if action == "od_reference_standard_read":
        task = tasks.calibration_reference_standard_read(float(payload["ir_led_intensity"]))
        try:
            readings = task(blocking=True, timeout=30)
        except HueyException as exc:
            raise ValueError("Reference standard reading timed out.") from exc
        _raise_if_task_failed(readings, "Reference standard reading failed.")
        return {"od_readings": readings}

    if action == "stirring_calibration":
        task = tasks.calibration_run_stirring(
            payload.get("min_dc"),
            payload.get("max_dc"),
        )
        try:
            calibration = task(blocking=True, timeout=120)
        except HueyException as exc:
            raise ValueError("Stirring calibration timed out.") from exc
        _raise_if_task_failed(calibration, "Stirring calibration failed.")
        return calibration

    if action == "read_voltage":
        task = tasks.calibration_read_voltage()
        try:
            voltage = task(blocking=True, timeout=10)
        except HueyException as exc:
            raise ValueError("Voltage read timed out.") from exc
        _raise_if_task_failed(voltage, "Voltage read failed.")
        return {"voltage": float(voltage)}

    raise ValueError("Unknown calibration action.")

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


# Endpoint to check the status of a background task. unit_api is required to ping workers (who only expose unit_api)
@unit_api_bp.route("/task_results/<task_id>", methods=["GET"])
def task_status(task_id: str):
    blob = {"task_id": task_id, "result_url_path": "/unit_api/task_results/" + task_id}
    try:
        task = huey.result(task_id)
    except TaskLockedException:
        return (
            jsonify(blob | {"status": "failed", "error": "could not complete task due to lock."}),
            500,
        )
    except TaskException as e:
        # huey wraps the exception, so lets reraise it.
        return (
            jsonify(blob | {"status": "failed", "error": str(e)}),
            500,
        )

    if task is None:
        return jsonify(blob | {"status": "pending or not present"}), 202
    elif isinstance(task, Exception):
        return jsonify(blob | {"status": "failed", "error": str(task)}), 500
    else:
        return jsonify(blob | {"status": "complete", "result": task}), 200


### SYSTEM


@unit_api_bp.route("/system/update/<target>", methods=["POST", "PATCH"])
def update_target(target: str) -> DelayedResponseReturnValue:
    if target not in ("app",):  # todo: firmware
        abort(404, description="Invalid target")

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
def update() -> DelayedResponseReturnValue:
    body = current_app.get_json(request.data, type=structs.ArgsOptionsEnvs)

    commands: tuple[str, ...] = tuple()
    commands += tuple(body.args)
    for option, value in body.options.items():
        commands += (f"--{option.replace('_', '-')}",)
        if value is not None:
            commands += (str(value),)

    task = tasks.pio_update(*commands)
    return create_task_response(task)


@unit_api_bp.route("/system/reboot", methods=["POST", "PATCH"])
def reboot() -> DelayedResponseReturnValue:
    """Reboots unit"""
    # TODO: only let requests from the leader do this. Use lighttpd conf for this.

    # don't reboot the leader right away, give time for any other posts/gets to occur.
    if HOSTNAME == get_leader_hostname():
        sleep(5)
    task = tasks.reboot()
    return create_task_response(task)


@unit_api_bp.route("/system/shutdown", methods=["POST", "PATCH"])
def shutdown() -> DelayedResponseReturnValue:
    """Shutdown unit"""
    task = tasks.shutdown()
    return create_task_response(task)


@unit_api_bp.route("/system/remove_file", methods=["POST", "PATCH"])
def remove_file() -> DelayedResponseReturnValue:
    task_name = "remove_file"
    disallow_file = Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_FILE_SYSTEM"
    if os.path.isfile(disallow_file):
        publish_to_error_log(f"Delete blocked because {disallow_file} is present", task_name)
        abort(403, "DISALLOW_UI_FILE_SYSTEM is present")

    # use filepath in body
    body = current_app.get_json(request.data) or {}
    filepath = body.get("filepath")
    if not filepath:
        abort(400, "filepath field is required")
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
        abort(403, "Access to this path is not allowed")

    task = tasks.rm(str(candidate_path))
    return create_task_response(task)


# GET clock time
@unit_api_bp.route("/system/utc_clock", methods=["GET"])
def get_clock_time():
    try:
        current_time = current_utc_timestamp()
        return jsonify({"status": "success", "clock_time": current_time}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# PATCH / POST to set clock time
@unit_api_bp.route("/system/utc_clock", methods=["PATCH", "POST"])
def set_clock_time() -> DelayedResponseReturnValue:  # type: ignore[return]
    if HOSTNAME == get_leader_hostname():
        data = request.get_json(silent=True)  # don't throw 415
        if not data:
            abort(400, "utc_clock_time field is required")

        new_time = data.get("utc_clock_time")
        if not new_time:
            abort(400, "utc_clock_time field is required")

        # validate the timestamp
        try:
            to_datetime(new_time)
        except ValueError:
            abort(400, "Invalid utc_clock_time format. Use ISO 8601.")

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
def dir_listing(req_path: str):
    if os.path.isfile(Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_FILE_SYSTEM"):
        abort(403, "DISALLOW_UI_FILE_SYSTEM is present")

    BASE_DIR = os.environ["DOT_PIOREACTOR"]

    # Safely join to prevent directory traversal
    safe_path = safe_join(BASE_DIR, req_path)
    if not safe_path:
        abort(403, "Invalid path.")

    # Check if the path actually exists
    if not os.path.exists(safe_path):
        abort(404, "Path not found.")

    # If it's a file, serve the file
    if os.path.isfile(safe_path):
        if safe_path.endswith((".sqlite", ".sqlite.backup", ".sqlite-shm", ".sqlite-wal")):
            abort(403, "Access to downloading sqlite files is restricted.")

        return send_file(safe_path, mimetype="text/plain")

    # Joining the base and the requested path
    abs_path = os.path.join(BASE_DIR, req_path)

    # Return 404 if path doesn't exist
    if not os.path.exists(abs_path):
        abort(404, "Path not found.")

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


@unit_api_bp.route("/jobs/run/job_name/<job>", methods=["PATCH", "POST"])
def run_job(job: str) -> DelayedResponseReturnValue:
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
    if is_rate_limited(job):
        abort(429, "Too many requests, please try again later.")

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

    commands: tuple[str, ...] = (job,)
    commands += tuple(args)
    for option, value in options.items():
        commands += (f"--{option.replace('_', '-')}",)
        if value is not None:
            commands += (str(value),)

    task = tasks.pio_run(*commands, env=env, config_overrides=config_overrides_as_flags)
    return create_task_response(task)


@unit_api_bp.route("/jobs/stop/all", methods=["PATCH", "POST"])
def stop_all_jobs() -> DelayedResponseReturnValue:
    task = tasks.pio_kill("--all-jobs")
    return create_task_response(task)


@unit_api_bp.route("/jobs/stop", methods=["PATCH", "POST"])
def stop_jobs() -> DelayedResponseReturnValue:
    if not request.data:
        return abort(400, "No job filter specified")
    json = current_app.get_json(request.data)

    job_name = json.get("job_name")
    experiment = json.get("experiment")
    job_source = json.get("job_source")
    job_id = json.get("job_id")
    if not any([job_name, experiment, job_source, job_id]):
        return abort(400, "No job filter specified")

    kill_args = []
    if job_name:
        kill_args.extend(["--job-name", job_name])
    if experiment:
        kill_args.extend(["--experiment", experiment])
    if job_source:
        kill_args.extend(["--job-source", job_source])
    if job_id:
        kill_args.extend(["--job-id", str(job_id)])  # note job_id is typically an int, convert to str

    task = tasks.pio_kill(*kill_args)
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


@unit_api_bp.route("/jobs/running/<job>", methods=["GET"])
def get_running_job(job: str) -> ResponseReturnValue:
    jobs = query_temp_local_metadata_db(
        "SELECT * FROM pio_job_metadata where is_running=1 and job_name=?", (job,)
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
def get_settings_for_a_specific_job(job_name: str) -> ResponseReturnValue:
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
        abort(404, "No settings found for job.")


@unit_api_bp.route("/jobs/settings/job_name/<job_name>/setting/<setting>", methods=["GET"])
def get_specific_setting_for_a_job(job_name: str, setting: str) -> ResponseReturnValue:
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
        abort(404, "Setting not found.")


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
    abort(503, "Not implemented.")


@unit_api_bp.route("/capabilities", methods=["GET"])
def discover_jobs_and_settings_available() -> ResponseReturnValue:
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
    result = tasks.pio_plugins_list("plugins", "list", "--json")
    try:
        status, msg = result(blocking=True, timeout=10)
    except HueyException:
        status, msg = False, "Timed out."

    if not status:
        abort(404, msg)
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
def get_plugin(filename: str) -> ResponseReturnValue:
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
        abort(404, "must provide a .py file")
    except Exception:
        abort(500, "server error")


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
        abort(403, "DISALLOW_UI_INSTALLS is present")

    # allowlist = _load_plugin_allowlist()
    # if not allowlist:
    #    abort(
    #        403,
    #        "Plugin installs via API are disabled: plugins_allowlist.json missing, empty, or invalid.",
    #    )

    body = current_app.get_json(request.data, type=structs.ArgsOptionsEnvs)

    if not body.args:
        abort(400, "Plugin name is required")
    if len(body.args) > 1:
        abort(400, "Install one plugin at a time via the API")

    # requested_plugin = _canonicalize_package_name(body.args[0])
    # if requested_plugin not in allowlist:
    #    abort(
    #        403,
    #        f"Plugin '{requested_plugin}' is not in the allowlist for API installs.",
    #    )

    commands: tuple[str, ...] = ("install",)
    commands += tuple(body.args)
    for option, value in body.options.items():
        commands += (f"--{option.replace('_', '-')}",)
        if value is not None:
            commands += (str(value),)

    task = tasks.pio_plugins(*commands)
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

    commands: tuple[str, ...] = ("uninstall",)
    commands += tuple(body.args)
    for option, value in body.options.items():
        commands += (f"--{option.replace('_', '-')}",)
        if value is not None:
            commands += (str(value),)

    task = tasks.pio_plugins(*commands)
    return create_task_response(task)


### VERSIONS


@unit_api_bp.route("/versions/app", methods=["GET"])
def get_app_version() -> ResponseReturnValue:
    return attach_cache_control(jsonify({"version": __version__}), max_age=30)


### CALIBRATIONS


@unit_api_bp.route("/calibrations/sessions", methods=["POST"])
def start_calibration_session() -> ResponseReturnValue:
    body = request.get_json()
    if body is None:
        abort(400, description="Missing JSON payload.")

    protocol_name = body.get("protocol_name")
    target_device = body.get("target_device")
    if not target_device:
        abort(400, description="Missing 'target_device'.")

    try:
        if protocol_name == "duration_based":
            if target_device not in pt.PUMP_DEVICES:
                abort(400, description="Unsupported target device.")
            session = start_duration_based_session(target_device)
        elif protocol_name == "standards":
            if target_device not in pt.OD_DEVICES:
                abort(400, description="Unsupported target device.")
            session = start_standards_session(target_device)
        elif protocol_name == "od_reference_standard":
            if target_device not in pt.OD_DEVICES:
                abort(400, description="Unsupported target device.")
            session = start_reference_standard_session(target_device)
        elif protocol_name == "dc_based":
            if target_device != "stirring":
                abort(400, description="Unsupported target device.")
            session = start_dc_based_session(target_device)
        else:
            abort(400, description="Unsupported protocol.")
    except ValueError as exc:
        abort(400, description=str(exc))

    save_calibration_session(session)
    if session.protocol_name == "duration_based":
        step = get_duration_based_step(session)
    elif session.protocol_name == "standards":
        step = get_standards_step(session)
    elif session.protocol_name == "od_reference_standard":
        step = get_reference_standard_step(session)
    elif session.protocol_name == "dc_based":
        step = get_dc_based_step(session)
    else:
        abort(400, description="Unsupported protocol.")
    step_payload = to_builtins(step) if step is not None else None
    return jsonify({"session": to_builtins(session), "step": step_payload}), 201


@unit_api_bp.route("/calibrations/sessions/<session_id>", methods=["GET"])
def get_calibration_session(session_id: str) -> ResponseReturnValue:
    session = load_calibration_session(session_id)
    if session is None:
        abort(404, description="Calibration session not found.")
    if session.protocol_name == "duration_based":
        step = get_duration_based_step(session)
    elif session.protocol_name == "standards":
        step = get_standards_step(session)
    elif session.protocol_name == "od_reference_standard":
        step = get_reference_standard_step(session)
    elif session.protocol_name == "dc_based":
        step = get_dc_based_step(session)
    else:
        abort(400, description="Unsupported protocol.")
    step_payload = to_builtins(step) if step is not None else None
    return jsonify({"session": to_builtins(session), "step": step_payload}), 200


@unit_api_bp.route("/calibrations/sessions/<session_id>/abort", methods=["POST"])
def abort_calibration_session_route(session_id: str) -> ResponseReturnValue:
    session = load_calibration_session(session_id)
    if session is None:
        abort(404, description="Calibration session not found.")

    abort_calibration_session(session_id)
    session = load_calibration_session(session_id)
    if session is None:
        abort(404, description="Calibration session not found.")
    if session.protocol_name == "duration_based":
        step = get_duration_based_step(session)
    elif session.protocol_name == "standards":
        step = get_standards_step(session)
    elif session.protocol_name == "od_reference_standard":
        step = get_reference_standard_step(session)
    elif session.protocol_name == "dc_based":
        step = get_dc_based_step(session)
    else:
        abort(400, description="Unsupported protocol.")
    step_payload = to_builtins(step) if step is not None else None
    return jsonify({"session": to_builtins(session), "step": step_payload}), 200


@unit_api_bp.route("/calibrations/sessions/<session_id>/inputs", methods=["POST"])
def advance_calibration_session(session_id: str) -> ResponseReturnValue:
    session = load_calibration_session(session_id)
    if session is None:
        abort(404, description="Calibration session not found.")

    body = request.get_json()
    if body is None:
        abort(400, description="Missing JSON payload.")

    inputs = body.get("inputs", {})
    if not isinstance(inputs, dict):
        abort(400, description="Invalid inputs payload.")

    try:
        if session.protocol_name == "duration_based":
            session = advance_duration_based_session(session, inputs, executor=_execute_calibration_action)
        elif session.protocol_name == "standards":
            session = advance_standards_session(session, inputs, executor=_execute_calibration_action)
        elif session.protocol_name == "od_reference_standard":
            session = advance_reference_standard_session(session, inputs, executor=_execute_calibration_action)
        elif session.protocol_name == "dc_based":
            session = advance_dc_based_session(session, inputs, executor=_execute_calibration_action)
        else:
            abort(400, description="Unsupported protocol.")
    except ValueError as exc:
        abort(400, description=str(exc))

    save_calibration_session(session)
    if session.protocol_name == "duration_based":
        step = get_duration_based_step(session)
    elif session.protocol_name == "standards":
        step = get_standards_step(session)
    elif session.protocol_name == "od_reference_standard":
        step = get_reference_standard_step(session)
    elif session.protocol_name == "dc_based":
        step = get_dc_based_step(session)
    else:
        abort(400, description="Unsupported protocol.")
    step_payload = to_builtins(step) if step is not None else None
    return jsonify({"session": to_builtins(session), "step": step_payload}), 200


@unit_api_bp.route("/calibrations/<device>", methods=["POST"])
def create_calibration(device: str) -> ResponseReturnValue:
    """
    Create a new calibration for the specified device.
    """
    # calibration_dir = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations" / device
    # if folder does not exist, users should make it with mkdir -p ... && chown -R pioreactor:www-data ...

    try:
        raw_yaml = request.get_json()["calibration_data"]
        calibration_data = yaml_decode(raw_yaml, type=AllCalibrations)
        calibration_name = calibration_data.calibration_name

        if not calibration_name or not is_valid_unix_filename(calibration_name):
            abort(400, description="Missing or invalid 'calibration_name'.")
        elif not device or not is_valid_unix_filename(device):
            abort(400, description="Missing or invalid 'device'.")

        path = calibration_data.path_on_disk_for_device(device)
        tasks.save_file(path, raw_yaml)

        # Respond with success and the created calibration details
        return jsonify({"msg": "Calibration created successfully.", "path": str(path)}), 201

    except Exception as e:
        publish_to_error_log(f"Error creating calibration: {e}", "create_calibration")
        abort(500, description="Failed to create calibration.")


@unit_api_bp.route("/calibrations/<device>/<calibration_name>", methods=["DELETE"])
def delete_calibration(device: str, calibration_name: str) -> ResponseReturnValue:
    """
    Delete a specific calibration for a given device.
    """
    calibration_path = (
        Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations" / device / f"{calibration_name}.yaml"
    )

    if not calibration_path.exists():
        abort(404, description=f"Calibration '{calibration_name}' not found for device '{device}'.")

    try:
        # Remove the calibration file
        calibration_path.unlink()

        # If the deleted calibration was active, remove its active status
        with local_persistent_storage("active_calibrations") as cache:
            if cache.get(device) == calibration_name:
                cache.pop(device)

        return (
            jsonify({"msg": f"Calibration '{calibration_name}' for device '{device}' deleted successfully."}),
            200,
        )

    except Exception as e:
        publish_to_error_log(f"Error deleting calibration: {e}", "delete_calibration")
        abort(500, description="Failed to delete calibration.")


@unit_api_bp.route("/calibrations", methods=["GET"])
def get_all_calibrations() -> ResponseReturnValue:
    calibration_dir = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations"

    if not calibration_dir.exists():
        abort(404, "Calibration directory does not exist.")

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
    calibration_dir = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations"

    if not calibration_dir.exists():
        abort(404, "Calibration directory does not exist.")

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


@unit_api_bp.route("/zipped_calibrations", methods=["GET"])
def get_all_calibrations_as_zipped_yaml() -> ResponseReturnValue:
    calibration_dir = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations"

    if not calibration_dir.exists():
        abort(404, "Calibration directory does not exist.")

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
def get_entire_dot_pioreactor_as_zip() -> ResponseReturnValue:
    """Create and return a ZIP of the entire DOT_PIOREACTOR directory.

    Notes:
    - Respects DISALLOW_UI_FILE_SYSTEM flag for parity with directory browsing.
    - Uses a temp file on disk to avoid holding large zips in memory.
    - Zips all contents recursively with paths relative to DOT_PIOREACTOR.
    """
    if os.path.isfile(Path(os.environ["DOT_PIOREACTOR"]) / "DISALLOW_UI_FILE_SYSTEM"):
        abort(403, "DISALLOW_UI_FILE_SYSTEM is present")

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
    if os.path.isfile(disallow_file):
        publish_to_error_log(f"Import blocked because {disallow_file} is present", task_name)
        abort(403, "DISALLOW_UI_FILE_SYSTEM is present")

    uploaded = request.files.get("archive")
    if uploaded is None or uploaded.filename == "":
        publish_to_error_log("No archive uploaded in import request", task_name)
        abort(400, "No archive uploaded")

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
        abort(400, str(exc))
    except zipfile.BadZipFile:
        publish_to_error_log("Uploaded file is not a valid zip archive", task_name)
        tmp_path.unlink(missing_ok=True)
        abort(400, "Uploaded file is not a valid zip archive")
    except Exception as exc:
        publish_to_error_log(f"Failed to inspect uploaded archive: {exc}", task_name)
        tmp_path.unlink(missing_ok=True)
        abort(500, "Failed to inspect uploaded archive")

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
        abort(500, "Failed to enqueue import task")
    except Exception as exc:  # pragma: no cover - unexpected failure
        publish_to_error_log(f"Failed to enqueue import task: {exc}", task_name)
        tmp_path.unlink(missing_ok=True)
        abort(500, "Failed to enqueue import task")

    publish_to_log("Import task submitted to Huey", task_name, "DEBUG")
    return create_task_response(task)


@unit_api_bp.route("/calibrations/<device>", methods=["GET"])
def get_calibrations_by_device(device: str) -> ResponseReturnValue:
    calibration_dir = Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations" / device

    if not calibration_dir.exists():
        abort(404, "Calibration directory does not exist.")

    calibrations: list[dict] = []

    with local_persistent_storage("active_calibrations") as c:
        for file in sorted(calibration_dir.glob("*.yaml")):
            try:
                # first try to open it using our struct, but only to verify it.
                cal = to_builtins(yaml_decode(file.read_bytes(), type=AllCalibrations))
                cal["is_active"] = c.get(device) == cal["calibration_name"]
                cal["pioreactor_unit"] = HOSTNAME
                calibrations.append(cal)
            except Exception as e:
                publish_to_error_log(f"Error reading {file.stem}: {e}", "get_calibrations_by_device")

    return attach_cache_control(jsonify(calibrations), max_age=10)


@unit_api_bp.route("/calibrations/<device>/<cal_name>", methods=["GET"])
def get_calibration(device: str, cal_name: str) -> ResponseReturnValue:
    calibration_path = (
        Path(os.environ["DOT_PIOREACTOR"]) / "storage" / "calibrations" / device / f"{cal_name}.yaml"
    )

    if not calibration_path.exists():
        abort(404, "Calibration file does not exist.")

    with local_persistent_storage("active_calibrations") as c:
        try:
            cal = to_builtins(yaml_decode(calibration_path.read_bytes(), type=AllCalibrations))
            cal["is_active"] = c.get(device) == cal["calibration_name"]
            cal["pioreactor_unit"] = HOSTNAME
            return attach_cache_control(jsonify(cal), max_age=10)
        except Exception as e:
            publish_to_error_log(f"Error reading {calibration_path.stem}: {e}", "get_calibration")
            abort(500, "Failed to read calibration file.")


@unit_api_bp.route("/active_calibrations/<device>/<cal_name>", methods=["PATCH"])
def set_active_calibration(device: str, cal_name: str) -> ResponseReturnValue:
    with local_persistent_storage("active_calibrations") as c:
        c[device] = cal_name

    return {"status": "success"}, 200


@unit_api_bp.route("/active_calibrations/<device>", methods=["DELETE"])
def remove_active_status_calibration(device: str) -> ResponseReturnValue:
    with local_persistent_storage("active_calibrations") as c:
        if device in c:
            c.pop(device)

    return {"status": "success"}, 200


@unit_api_bp.errorhandler(404)
def not_found(e):
    # Return JSON for API requests, using the error description
    return jsonify({"error": e.description}), 404
