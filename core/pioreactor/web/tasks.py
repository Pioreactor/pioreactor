# -*- coding: utf-8 -*-
"""
Huey background tasks used by the web API, including calibration actions invoked
from `core/pioreactor/web/unit_calibration_sessions_api.py` via the session executor.
This module also hosts the calibration action registry that maps action names
to Huey tasks so unit API handlers can dispatch without hardcoded strings.
"""
# -*- coding: utf-8 -*-
import configparser
import grp
import json
import logging
import os
import pwd
import shutil
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path
from shlex import join
from subprocess import check_call
from subprocess import DEVNULL
from subprocess import Popen
from subprocess import run
from subprocess import TimeoutExpired
from tempfile import mkdtemp
from time import sleep
from typing import Any
from typing import cast

from huey.exceptions import ResultTimeout
from huey.exceptions import TaskException
from msgspec import DecodeError
from pioreactor import exc
from pioreactor import hardware
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.config import config as pioreactor_config
from pioreactor.logging import create_logger
from pioreactor.mureq import HTTPErrorStatus
from pioreactor.mureq import HTTPException
from pioreactor.mureq import Response
from pioreactor.pubsub import delete_from
from pioreactor.pubsub import get_from
from pioreactor.pubsub import patch_into
from pioreactor.pubsub import post_into
from pioreactor.utils.networking import resolve_to_address
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.web.config import huey
from pioreactor.whoami import get_unit_name

CalibrationActionHandler = tuple[
    Any,
    str,
    Callable[[Any], dict[str, Any]],
]

# Registry of calibration action -> handler that returns a Huey task, label, and normalizer.
calibration_actions: dict[str, Callable[[dict[str, Any]], CalibrationActionHandler]] = {}


def register_calibration_action(
    action: str,
    handler: Callable[[dict[str, Any]], CalibrationActionHandler],
) -> None:
    calibration_actions[action] = handler


def get_calibration_action(action: str) -> Callable[[dict[str, Any]], CalibrationActionHandler]:
    handler = calibration_actions.get(action)
    if handler is None:
        raise ValueError(f"Unknown calibration action: {action}")
    return handler


logger = create_logger(
    "background_tasks",
    source="huey",
    experiment="$experiment",
    log_file_location=pioreactor_config["logging"]["ui_log_file"],
)

logger.setLevel(logging.DEBUG)

# NOTE: we use logger.debug here else the UI's log tables can get filled with red errors.

PIO_EXECUTABLE = os.environ["PIO_EXECUTABLE"]
PIOS_EXECUTABLE = os.environ["PIOS_EXECUTABLE"]

ALLOWED_ENV = (
    "EXPERIMENT",
    "JOB_SOURCE",
    "TESTING",
    "HOSTNAME",
    "HARDWARE",
    "ACTIVE",
    "FIRMWARE",
    "ACTIVE",
    "DEBUG",
    "MODEL_NAME",
    "MODEL_VERSION",
    "SKIP_PLUGINS",
    "DOT_PIOREACTOR",
    "GLOBAL_CONFIG",
    "LOCAL_CONFIG",
)


def _safe_zip_members(members: list[zipfile.ZipInfo]) -> None:
    for member in members:
        filename = member.filename
        if filename.startswith("/"):
            raise ValueError("Archive contains absolute paths, aborting import.")
        path = Path(filename)
        if ".." in path.parts:
            raise ValueError("Archive contains path traversal, aborting import.")
        is_symlink = member.external_attr >> 16 & 0o120000 == 0o120000
        if is_symlink:
            raise ValueError("Archive contains symbolic links, aborting import.")


def _apply_ownership(target: Path, user: str, group: str) -> None:
    try:
        uid = pwd.getpwnam(user).pw_uid
        gid = grp.getgrnam(group).gr_gid
    except KeyError:
        logger.error(f"Unable to resolve ownership for {user}:{group}")
        return

    for root, dirs, files in os.walk(target):
        _chown_directory(Path(root), uid, gid)
        for name in dirs:
            _chown_directory(Path(root) / name, uid, gid)
        for name in files:
            _chown_path(Path(root) / name, uid, gid)


def _chown_path(path: Path, uid: int, gid: int) -> None:
    try:
        os.chown(path, uid, gid)
    except PermissionError:
        logger.error(f"Failed to set ownership on {path}")


def _chown_directory(path: Path, uid: int, gid: int) -> None:
    try:
        os.chown(path, uid, gid)
    except PermissionError:
        logger.error(f"Failed to set ownership on {path}")
        return

    try:
        mode = path.stat().st_mode
        if not mode & stat.S_ISGID:
            os.chmod(path, mode | stat.S_ISGID)
    except PermissionError:
        logger.error(f"Failed to apply setgid on {path}")


def validate_dot_pioreactor_archive(
    archive_path: str | Path, expected_hostname: str
) -> dict[str, Any] | None:
    """
    Performs validation on a zipped DOT_PIOREACTOR archive.
    Returns parsed metadata (if available) after enforcing hostname constraints.
    Raises ValueError on validation failures.
    """
    path = Path(archive_path)
    with zipfile.ZipFile(path, "r") as zf:
        _safe_zip_members(zf.infolist())
        try:
            metadata_bytes = zf.read("pioreactor_export_metadata.json")
        except KeyError:
            return None
        try:
            metadata = json.loads(metadata_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Archive metadata invalid") from exc

        exported_name = metadata.get("name")
        if exported_name and exported_name != expected_hostname:
            raise ValueError(f"Archive prepared for {exported_name}, cannot import into {expected_hostname}")
        return metadata


def filter_to_allowed_env(env: dict):
    """
    Filter the environment dictionary to only include allowed keys.
    This is used to prevent passing sensitive or unnecessary environment variables.
    """
    env = os.environ | env
    return {k: v for k, v in env.items() if k in ALLOWED_ENV and v is not None and v != "" and v != "None"}


def _process_delayed_json_response(
    unit: str,
    response: Response,
    *,
    max_attempts: int = 60,
    retry_sleep_s: float = 0.1,
) -> tuple[str, Any]:
    """
    Handle delayed HTTP responses (202 with result_url_path) and immediate 200 responses.
    Returns the unit and the appropriate JSON data or result value.
    """
    data = response.json()
    if response.status_code == 202 and "result_url_path" in data:
        # Follow up shortly on async responses where the unit returns a result URL.
        if max_attempts <= 0:
            return unit, None
        sleep(retry_sleep_s)
        return _get_from_unit(unit, data["result_url_path"], max_attempts=max_attempts - 1)
    if response.status_code == 200:
        # Normalize immediate responses: unwrap Huey-style payloads to just the result,
        # otherwise return the full JSON body for non-task responses.
        if "task_id" in data:
            return unit, data["result"]
        else:
            return unit, data
    return unit, None


@huey.on_startup()
def initialized():
    logger.debug("Starting Huey consumer...")


@huey.task(priority=50)
def pio_run(
    *args: str,
    env: dict[str, str] | None = None,
    config_overrides: tuple[str, ...] = (),
    grace_s: float = 0.5,  # how long to watch for "fast-fail"
) -> bool:
    command = (PIO_EXECUTABLE, "run") + config_overrides + args

    env = filter_to_allowed_env(env or {})

    logger.debug(f"Executing `{join(command)}`, {env=}")

    try:
        proc = Popen(
            command,
            start_new_session=True,  # detach from our session
            env=env,
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=DEVNULL,
            close_fds=True,
        )
    except Exception:
        logger.error("Failed to spawn %r", command)
        return False

    # If it exits during the grace window, it probably failed fast (e.g., bad args).
    try:
        proc.wait(timeout=grace_s)
    except TimeoutExpired:
        # Still running after the grace window: treat as "started successfully".
        return True
    else:
        return False


@huey.task()
def add_new_pioreactor(new_pioreactor_name: str, version: str, model: str) -> bool:
    command = [PIO_EXECUTABLE, "workers", "add", new_pioreactor_name, "-v", version, "-m", model]
    logger.debug(f"Executing `{join(command)}`")
    check_call(command)
    return True


def _get_adc_addresses_for_model(model_name: str, model_version: str) -> set[int]:
    adc_cfg = hardware.get_layered_mod_config_for_model("adc", model_name, model_version)
    addresses: set[int] = set()
    for adc_data in adc_cfg.values():
        address = adc_data.get("address")
        addresses.add(int(address))
    return addresses


@huey.task(priority=10)
def check_model_hardware(model_name: str, model_version: str) -> None:
    if model_version != "1.5":
        return

    try:
        addresses = _get_adc_addresses_for_model(model_name, model_version)
    except exc.HardwareNotFoundError as err:
        logger.warning(
            f"Hardware check skipped on {get_unit_name()}: {err}",
        )
        return

    if not addresses:
        logger.debug(
            f"Hardware check found no ADC addresses for {model_name} {model_version} on {get_unit_name()}."
        )
        return

    missing = sorted(addr for addr in addresses if not hardware.is_i2c_device_present(addr))
    if missing:
        missing_hex = ", ".join(hex(addr) for addr in missing)
        logger.warning(
            f"Hardware check failed for {model_name} {model_version} on {get_unit_name()}: "
            f"missing I2C devices at {missing_hex}."
        )
        return

    logger.notice(f"Correct hardware found for {model_name} {model_version} on {get_unit_name()}.")
    return


@huey.task()
def update_app_across_cluster() -> bool:
    # CPU heavy / IO heavy
    logger.debug("Updating app on leader")
    update_app_on_leader = ["pio", "update", "app"]
    check_call(update_app_on_leader)

    logger.debug("Updating app on workers")
    update_app_across_all_workers = [PIOS_EXECUTABLE, "update", "-y"]
    run(update_app_across_all_workers)
    return True


@huey.task()
def update_app_from_release_archive_across_cluster(archive_location: str, units: str) -> bool:
    if units == "$broadcast":
        logger.debug(f"Updating app on leader from {archive_location}")
        update_app_on_leader = [
            "pio",
            "update",
            "app",
            "--source",
            archive_location,
            "--defer-web-restart",
        ]
        check_call(update_app_on_leader)

        logger.debug(f"Updating app on workers from {archive_location}")
        distribute_archive_to_workers = [PIOS_EXECUTABLE, "cp", archive_location, "-y"]
        run(distribute_archive_to_workers)

        # this may include leader, and leader's UI. If it's not included, we need to update the UI later.
        update_app_across_all_workers = [
            PIOS_EXECUTABLE,
            "update",
            "--source",
            archive_location,
            "-y",
        ]
        run(update_app_across_all_workers)

        logger.debug("Restarting pioreactor-web.target after cluster update")
        check_call(["sudo", "systemctl", "restart", "pioreactor-web.target"])

        return True
    else:
        logger.debug(f"Updating app on unit {units} from {archive_location}")
        distribute_archive_to_workers = [
            PIOS_EXECUTABLE,
            "cp",
            archive_location,
            "-y",
            "--units",
            units,
        ]
        run(distribute_archive_to_workers)

        update_app_across_all_workers = [
            PIOS_EXECUTABLE,
            "update",
            "--source",
            archive_location,
            "-y",
            "--units",
            units,
        ]
        run(update_app_across_all_workers)
        return True


@huey.task()
def update_app_from_release_archive_on_specific_pioreactors(
    archive_location: str, pioreactors: list[str]
) -> bool:
    units_cli: tuple[str, ...] = sum((("--units", p) for p in pioreactors), tuple())

    logger.debug(f"Updating app and ui on unit {pioreactors} from {archive_location}")
    distribute_archive_to_workers = [PIOS_EXECUTABLE, "cp", archive_location, "-y", *units_cli]
    run(distribute_archive_to_workers)

    update_app_across_all_workers = [
        PIOS_EXECUTABLE,
        "update",
        "--source",
        archive_location,
        "-y",
        *units_cli,
    ]
    run(update_app_across_all_workers)

    return True


@huey.task()
def pio(*args: str, env: dict[str, str] | None = None) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio",) + args)}`, {env=}')
    result = run(
        (PIO_EXECUTABLE,) + args,
        env=env,
        stdout=DEVNULL,
        stderr=DEVNULL,
    )
    return result.returncode == 0


@huey.task()
def list_plugins_installed() -> tuple[bool, str]:
    from pioreactor.plugin_management.list_plugins import list_plugins_as_json

    try:
        return True, list_plugins_as_json()
    except Exception as exc:
        logger.debug(str(exc))
        return False, str(exc)


@huey.task()
def calibration_execute_pump(pump_device: str, duration_s: float, hz: float, dc: float) -> bool:
    from pioreactor.calibrations.protocols.pump_duration_based import _build_transient_calibration
    from pioreactor.calibrations.protocols.pump_duration_based import _get_execute_pump_for_device
    from pioreactor.whoami import get_testing_experiment_name

    logger.debug(
        "Starting pump calibration action: device=%s duration_s=%s hz=%s dc=%s",
        pump_device,
        duration_s,
        hz,
        dc,
    )
    execute_pump = _get_execute_pump_for_device(cast(pt.PumpCalibrationDevices, pump_device))
    calibration = _build_transient_calibration(hz=hz, dc=dc, unit=get_unit_name())
    execute_pump(
        duration=duration_s,
        source_of_event="pump_calibration",
        unit=get_unit_name(),
        experiment=get_testing_experiment_name(),
        calibration=calibration,
    )
    logger.debug("Finished pump calibration action for device=%s", pump_device)
    return True


@huey.task()
def calibration_measure_standard(
    rpm: float,
    channel_angle_map: dict[str, str],
) -> dict[str, float]:
    from pioreactor.calibrations.protocols.od_standards import _measure_standard

    logger.debug(
        "Starting OD standards measurement: rpm=%s channels=%s",
        rpm,
        sorted(channel_angle_map.keys()),
    )
    typed_map = {
        cast(pt.PdChannel, channel): cast(pt.PdAngle, angle) for channel, angle in channel_angle_map.items()
    }
    voltages = _measure_standard(
        od600_value=0.0,
        rpm=rpm,
        channel_angle_map=typed_map,
    )
    logger.debug("Finished OD standards measurement: rpm=%s", rpm)
    return {str(channel): float(voltage) for channel, voltage in voltages.items()}


@huey.task()
def calibration_fusion_standards_measure(
    od_value: float,
    rpm: float,
    samples_per_standard: int,
) -> dict[str, object]:
    from pioreactor.calibrations.protocols.od_fusion_standards import _measure_fusion_standard

    logger.debug(
        "Starting fusion OD measurement: od_value=%s rpm=%s samples_per_standard=%s",
        od_value,
        rpm,
        samples_per_standard,
    )
    samples = _measure_fusion_standard(
        od_value=od_value,
        rpm=rpm,
        samples_per_standard=samples_per_standard,
    )
    serialized_samples: list[dict[str, float]] = []
    for sample in samples:
        serialized_samples.append({str(angle): float(value) for angle, value in sample.items()})
    logger.debug(
        "Finished fusion OD measurement: od_value=%s rpm=%s sample_count=%s",
        od_value,
        rpm,
        len(serialized_samples),
    )
    return {"samples": serialized_samples}


@huey.task()
def calibration_run_stirring(min_dc: float | None, max_dc: float | None) -> dict[str, object]:
    from pioreactor.calibrations.protocols.stirring_dc_based import collect_stirring_measurements

    logger.debug("Starting stirring calibration: min_dc=%s max_dc=%s", min_dc, max_dc)
    dcs, rpms = collect_stirring_measurements(min_dc=min_dc, max_dc=max_dc)
    logger.debug(
        "Finished stirring calibration: min_dc=%s max_dc=%s steps=%s",
        min_dc,
        max_dc,
        len(dcs),
    )
    return {"dcs": dcs, "rpms": rpms}


@huey.task()
def calibration_save_calibration(device: str, calibration_payload: dict[str, object]) -> dict[str, str]:
    from msgspec.json import decode as json_decode
    from msgspec.json import encode as json_encode
    from pioreactor.structs import CalibrationBase
    from pioreactor.structs import subclass_union

    logger.debug(
        "Starting calibration save: device=%s payload_keys=%s",
        device,
        sorted(calibration_payload.keys()),
    )
    all_calibrations = subclass_union(CalibrationBase)
    calibration = json_decode(json_encode(calibration_payload), type=all_calibrations)
    path = calibration.save_to_disk_for_device(device)
    calibration.set_as_active_calibration_for_device(device)
    logger.debug(
        "Finished calibration save: device=%s calibration_name=%s path=%s",
        device,
        calibration.calibration_name,
        path,
    )
    return {"path": path, "device": device, "calibration_name": calibration.calibration_name}


@huey.task()
def estimator_save_estimator(device: str, estimator_payload: dict[str, object]) -> dict[str, str]:
    from msgspec.json import decode as json_decode
    from msgspec.json import encode as json_encode
    from pioreactor.structs import ODFusionEstimator

    logger.debug(
        "Starting estimator save: device=%s payload_keys=%s",
        device,
        sorted(estimator_payload.keys()),
    )
    estimator = json_decode(json_encode(estimator_payload), type=ODFusionEstimator)
    path = estimator.save_to_disk_for_device(device)
    estimator.set_as_active_calibration_for_device(device)
    logger.debug(
        "Finished estimator save: device=%s estimator_name=%s path=%s",
        device,
        estimator.estimator_name,
        path,
    )
    return {"path": path, "device": device, "estimator_name": estimator.estimator_name}


@huey.task()
def calibration_read_voltage() -> float:
    from pioreactor.hardware import voltage_in_aux

    logger.debug("Starting aux voltage read")
    voltage = float(voltage_in_aux())
    logger.debug("Finished aux voltage read: voltage=%s", voltage)
    return voltage


def _default_normalizer(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    return {}


def _voltage_normalizer(result: Any) -> dict[str, Any]:
    return {"voltage": float(result)}


def _voltages_normalizer(result: Any) -> dict[str, Any]:
    return {"voltages": result}


def _od_readings_normalizer(result: Any) -> dict[str, Any]:
    return {"od_readings": result}


def _stirring_normalizer(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    return {}


def _register_core_calibration_actions() -> None:
    register_calibration_action(
        "pump",
        lambda payload: (
            calibration_execute_pump(
                payload["pump_device"],
                float(payload["duration_s"]),
                float(payload["hz"]),
                float(payload["dc"]),
            ),
            "Pump action",
            _default_normalizer,
        ),
    )
    register_calibration_action(
        "od_standards_measure",
        lambda payload: (
            calibration_measure_standard(
                float(payload["rpm"]),
                payload["channel_angle_map"],
            ),
            "OD measurement",
            _voltages_normalizer,
        ),
    )
    register_calibration_action(
        "od_fusion_standards_measure",
        lambda payload: (
            calibration_fusion_standards_measure(
                float(payload["od_value"]),
                float(payload["rpm"]),
                int(payload["samples_per_standard"]),
            ),
            "Fusion OD measurement",
            _default_normalizer,
        ),
    )
    register_calibration_action(
        "stirring_calibration",
        lambda payload: (
            calibration_run_stirring(
                float(payload["min_dc"]) if (payload.get("min_dc") is not None) else None,
                float(payload["max_dc"]) if (payload.get("max_dc") is not None) else None,
            ),
            "Stirring calibration",
            _stirring_normalizer,
        ),
    )
    register_calibration_action(
        "read_aux_voltage",
        lambda payload: (
            calibration_read_voltage(),
            "Aux voltage read",
            _voltage_normalizer,
        ),
    )
    register_calibration_action(
        "save_calibration",
        lambda payload: (
            calibration_save_calibration(
                payload["device"],
                payload["calibration"],
            ),
            "Saving calibration",
            _default_normalizer,
        ),
    )
    register_calibration_action(
        "save_estimator",
        lambda payload: (
            estimator_save_estimator(
                payload["device"],
                payload["estimator"],
            ),
            "Saving estimator",
            _default_normalizer,
        ),
    )


_register_core_calibration_actions()


@huey.task()
@huey.lock_task("export-data-lock")
def export_experiment_data_task(
    experiments: list[str],
    dataset_names: list[str],
    output: str,
    start_time: str | None = None,
    end_time: str | None = None,
    partition_by_unit: bool = False,
    partition_by_experiment: bool = True,
) -> tuple[bool, str]:
    from pioreactor.actions.leader.export_experiment_data import export_experiment_data

    logger.debug("Exporting experiment data.")
    if not output:
        return False, "Missing output"
    if not output.endswith(".zip"):
        return False, "output should end with .zip"
    if not dataset_names:
        return False, "At least one dataset name must be provided."

    try:
        export_experiment_data(
            experiments,
            dataset_names,
            output,
            start_time=start_time,
            end_time=end_time,
            partition_by_unit=partition_by_unit,
            partition_by_experiment=partition_by_experiment,
        )
        return True, "Finished"
    except Exception as exc:
        logger.debug(str(exc))
        return False, str(exc)


@huey.task(priority=100)
def kill_jobs_task(
    job_name: str | None = None,
    experiment: str | None = None,
    job_source: str | None = None,
    job_id: int | None = None,
    all_jobs: bool = False,
) -> bool:
    if not any([job_name, experiment, job_source, job_id, all_jobs]):
        logger.debug("No job filters provided for kill.")
        return False

    from pioreactor.background_jobs.base import JobManager

    try:
        with JobManager() as jm:
            count = jm.kill_jobs(
                all_jobs=all_jobs,
                job_name=job_name,
                experiment=experiment,
                job_source=job_source,
                job_id=job_id,
            )
        logger.debug(f"Killed {count} job{'s' if count != 1 else ''}.")
        return True
    except Exception as exc:
        logger.debug(str(exc))
        return False


@huey.task()
@huey.lock_task("plugins-lock")
def install_plugin_task(name: str, source: str | None = None) -> bool:
    from pioreactor.plugin_management.install_plugin import install_plugin

    logger.debug(f"Installing plugin {name}.")
    try:
        install_plugin(name, source=source)
        return True
    except Exception as exc:
        logger.debug(str(exc))
        return False


@huey.task()
@huey.lock_task("plugins-lock")
def uninstall_plugin_task(name: str) -> bool:
    from pioreactor.plugin_management.uninstall_plugin import uninstall_plugin

    logger.debug(f"Uninstalling plugin {name}.")
    try:
        uninstall_plugin(name)
        return True
    except Exception as exc:
        logger.debug(str(exc))
        return False


@huey.task()
def update_clock(new_time: str) -> bool:
    # iso8601 format
    if whoami.is_testing_env():
        return True
    r = run(["sudo", "date", "-s", new_time])
    return r.returncode == 0


@huey.task()
def sync_clock() -> bool:
    if whoami.is_testing_env():
        return True
    run(["sudo", "systemctl", "stop", "chrony"])
    run(["sudo", "chronyd", "-q"])
    r = run(["sudo", "systemctl", "start", "chrony"])
    return r.returncode == 0


@huey.task()
def import_dot_pioreactor_archive(uploaded_zip_path: str) -> bool:
    hostname = get_unit_name()
    archive_path = Path(uploaded_zip_path)
    base_dir = Path(os.environ["DOT_PIOREACTOR"]).resolve()
    extraction_root = Path(mkdtemp(prefix="dot_pioreactor_import_"))
    backup_dir = Path(os.environ["TMPDIR"]) / f"{hostname}_dot_pioreactor_backup_{current_utc_timestamp()}"

    def log(level: str, message: str) -> None:
        getattr(logger, level.lower())(message)

    def restore_from_backup() -> None:
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
            if backup_dir.exists():
                for item in backup_dir.iterdir():
                    shutil.move(str(item), base_dir / item.name)
            log("info", "Restored DOT_PIOREACTOR contents from backup.")
        except Exception as exc:  # pragma: no cover - best-effort logging
            log("error", f"Failed to restore DOT_PIOREACTOR from backup: {exc}")
            raise

    if whoami.is_testing_env():
        log("debug", "Testing environment detected, skipping import.")
        return True

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extraction_root)
        log("debug", f"Extracted archive into {extraction_root}")
    except zipfile.BadZipFile:
        log("error", "Uploaded file is not a valid zip archive")
        raise
    except Exception as e:
        log("error", str(e))
        raise

    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
        if base_dir.exists():
            for item in base_dir.iterdir():
                shutil.move(str(item), backup_dir / item.name)
        log("debug", f"Backup completed at {backup_dir}")
    except Exception as exc:
        log("error", f"Failed to backup existing DOT_PIOREACTOR: {exc}")
        raise RuntimeError("Failed to backup existing DOT_PIOREACTOR") from exc

    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        for item in extraction_root.iterdir():
            shutil.move(str(item), base_dir / item.name)

        # hardcode a change =(
        config_path = base_dir / "config.ini"
        if config_path.exists():
            cfg = configparser.ConfigParser()
            cfg.read(config_path)
            cfg.setdefault("storage", {})
            cfg["storage"][
                "temporary_cache"
            ] = "/run/pioreactor/cache/local_intermittent_pioreactor_metadata.sqlite"
            with config_path.open("w") as fh:
                cfg.write(fh, space_around_delimiters=False)

        for required_dirs in ["ui", "hardware"]:
            required_dir_path = base_dir / required_dirs
            if not required_dir_path.exists():
                backup_required_dir_path = backup_dir / required_dirs
                if backup_required_dir_path.exists():
                    shutil.move(str(backup_required_dir_path), required_dir_path)
                    log("debug", f"{required_dirs} directory missing from import; restored from backup")
                else:
                    log(
                        "error",
                        f"{required_dirs} directory missing from import and no backup copy is available",
                    )

        log("debug", "DOT_PIOREACTOR contents moved into place")
    except Exception as exc:
        log("error", f"Failed to write new DOT_PIOREACTOR contents: {exc}")
        try:
            restore_from_backup()
        except Exception:
            pass
        raise RuntimeError("Failed to write new DOT_PIOREACTOR contents") from exc

    _apply_ownership(base_dir, "pioreactor", "www-data")
    reboot(wait=2)
    log("debug", "Reboot task enqueued.")
    log("info", "Import finished successfully.")
    return True


@huey.task()
@huey.lock_task("update-lock")
def pio_update_app(*args: str, env: dict[str, str] | None = None) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio", "update", "app") + args)}`, {env=}')
    result = run((PIO_EXECUTABLE, "update", "app") + args, env=env)
    return result.returncode == 0


@huey.task()
@huey.lock_task("update-lock")
def pio_update(*args: str, env: dict[str, str] | None = None) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio", "update") + args)}`, {env=}')
    run((PIO_EXECUTABLE, "update") + args, env=env)
    # HACK: this always returns >0 because it kills huey, I think, so just return true
    return True


@huey.task()
def rm(path: str) -> bool:
    logger.debug(f"Deleting {path}.")
    if whoami.is_testing_env():
        return True
    result = run(["rm", path])
    return result.returncode == 0


@huey.task()
def shutdown() -> bool:
    logger.debug("Shutting down now")
    if whoami.is_testing_env():
        return True
    result = run(["sudo", "shutdown", "-h", "now"])
    return result.returncode == 0


@huey.task()
def reboot(wait=0) -> bool:
    sleep(wait)
    logger.debug("Rebooting now")
    if whoami.is_testing_env():
        return True
    result = run(["sudo", "reboot"])
    return result.returncode == 0


@huey.task()
def restart_pioreactor_web_target() -> bool:
    logger.debug("Restarting pioreactor-web.target")
    if whoami.is_testing_env():
        return True
    result = run(["sudo", "systemctl", "restart", "pioreactor-web.target"])
    return result.returncode == 0


@huey.task()
def pios(*args: str, env: dict[str, str] | None = None) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pios",) + args + ("-y",))}`, {env=}')
    result = run(
        (PIOS_EXECUTABLE,) + args + ("-y",),
        env=env,
    )
    return result.returncode == 0


@huey.task()
def save_file(path: str, content: str) -> bool:
    try:
        with open(path, "w") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.debug(e)
        return False


@huey.task()
def write_config_and_sync(
    config_path: str, text: str, units: str, flags: tuple[str, ...] = (), env: dict[str, str] | None = None
) -> tuple[bool, str]:
    env = filter_to_allowed_env(env or {})
    try:
        with open(config_path, "w") as f:
            f.write(text)

        logger.debug(
            f'Executing `{join((PIOS_EXECUTABLE, "sync-configs", "--units", units) + flags)}`, {env=}'
        )

        result = run(
            (PIOS_EXECUTABLE, "sync-configs", "--units", units) + flags,
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        if result.returncode != 0:
            raise Exception(result.stderr.strip())

        return (True, "")

    except Exception as e:
        logger.debug(str(e))
        return (False, "Could not sync configs to all Pioreactors.")


@huey.task(priority=10)
def post_into_unit(
    unit: str, endpoint: str, json: dict | None = None, params: dict | None = None
) -> tuple[str, Any]:
    try:
        address = resolve_to_address(unit)
        r = post_into(address, endpoint, json=json, params=params, timeout=1)
        r.raise_for_status()

        if r.content is None:
            return unit, None

        # delayed or immediate JSON response
        return _process_delayed_json_response(unit, r)

    except (HTTPErrorStatus, HTTPException) as e:
        logger.debug(
            f"Could not post to {unit}'s {address=}/{endpoint=}, sent {json=} and returned {e}. Check connection? Check port?"
        )
        return unit, None
    except DecodeError:
        logger.debug(
            f"Could not decode response from {unit}'s {endpoint=}, sent {json=} and returned {r.body.decode()}."
        )
        return unit, None


def _collect_multicast_results(
    units: list[str],
    tasks: Any,
    timeout: float,
) -> dict[str, Any]:
    try:
        return {unit: response for (unit, response) in tasks.get(blocking=True, timeout=timeout)}
    except (ResultTimeout, TaskException):
        results: dict[str, Any] = {}
        for unit, result in zip(units, tasks):
            try:
                value = result.get(blocking=False)
            except TaskException:
                results[unit] = None
                continue
            if value is None:
                results[unit] = None
            else:
                _, response = value
                results[unit] = response
        return results


@huey.task(priority=50)
def multicast_post(
    endpoint: str,
    units: list[str],
    json: dict | list[dict | None] | None = None,
    params: dict | list[dict | None] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    if not isinstance(json, list):
        json = [json] * len(units)

    assert json is not None

    if not isinstance(params, list):
        params = [params] * len(units)

    tasks = post_into_unit.map(((units[i], endpoint, json[i], params[i]) for i in range(len(units))))

    return _collect_multicast_results(
        units, tasks, timeout
    )  # add a timeout so that we don't hold up a thread forever.


@huey.task(priority=10)
def get_from_unit(
    unit: str, endpoint: str, json: dict | None = None, timeout=5.0, return_raw=False
) -> tuple[str, Any]:
    return _get_from_unit(unit, endpoint, json=json, timeout=timeout, return_raw=return_raw)


def _get_from_unit(
    unit: str,
    endpoint: str,
    json: dict | None = None,
    timeout=5.0,
    return_raw=False,
    max_attempts: int = 60,
) -> tuple[str, Any]:
    try:
        address = resolve_to_address(unit)

        r = get_from(address, endpoint, json=json, timeout=timeout)
        r.raise_for_status()

        if return_raw:
            return unit, r.content or None

        # delayed or immediate JSON response
        return _process_delayed_json_response(unit, r, max_attempts=max_attempts)

    except (HTTPErrorStatus, HTTPException) as e:
        logger.debug(
            f"Could not get from {unit}'s {address=}, {endpoint=}, sent {json=} and returned {e}. Check connection? Check port?"
        )
        return unit, None
    except DecodeError:
        logger.debug(
            f"Could not decode response from {unit}'s {endpoint=}, sent {json=} and returned {r.body.decode()}."
        )
        return unit, None


@huey.task(priority=5)
def multicast_get(
    endpoint: str,
    units: list[str],
    json: dict | list[dict | None] | None = None,
    timeout: float = 5.0,
    return_raw=False,
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    if not isinstance(json, list):
        json = [json] * len(units)

    tasks = get_from_unit.map(((units[i], endpoint, json[i], timeout, return_raw) for i in range(len(units))))
    unsorted_responses = _collect_multicast_results(
        units, tasks, timeout
    )  # add a timeout so that we don't hold up a thread forever.

    return dict(sorted(unsorted_responses.items()))  # always sort alphabetically for downstream uses.


@huey.task(priority=50)
def patch_into_unit(unit: str, endpoint: str, json: dict | None = None) -> tuple[str, Any]:
    try:
        address = resolve_to_address(unit)
        r = patch_into(address, endpoint, json=json, timeout=1)
        r.raise_for_status()

        if r.content is None:
            return unit, None

        # delayed or immediate JSON response
        return _process_delayed_json_response(unit, r)

    except (HTTPErrorStatus, HTTPException) as e:
        logger.debug(
            f"Could not PATCH to {unit}'s {address=}/{endpoint=}, sent {json=} and returned {e}. Check connection? Check port?"
        )
        return unit, None
    except DecodeError:
        logger.debug(
            f"Could not decode response from {unit}'s {endpoint=}, sent {json=} and returned {r.body.decode()}."
        )
        return unit, None


@huey.task(priority=50)
def multicast_patch(
    endpoint: str, units: list[str], json: dict | None = None, timeout: float = 30.0
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    tasks = patch_into_unit.map(((unit, endpoint, json) for unit in units))

    return _collect_multicast_results(
        units, tasks, timeout
    )  # add a timeout so that we don't hold up a thread forever.


@huey.task(priority=10)
def delete_from_unit(unit: str, endpoint: str, json: dict | None = None) -> tuple[str, Any]:
    try:
        r = delete_from(resolve_to_address(unit), endpoint, json=json, timeout=1)
        r.raise_for_status()
        return unit, r.json() if r.content else None
    except (HTTPErrorStatus, HTTPException) as e:
        logger.debug(
            f"Could not DELETE {unit}'s {endpoint=}, sent {json=} and returned {e}. Check connection?"
        )
        return unit, None
    except DecodeError:
        logger.debug(
            f"Could not decode response from {unit}'s {endpoint=}, sent {json=} and returned {r.body.decode()}."
        )
        return unit, None


@huey.task(priority=5)
def multicast_delete(
    endpoint: str, units: list[str], json: dict | None = None, timeout: float = 30.0
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    tasks = delete_from_unit.map(((unit, endpoint, json) for unit in units))

    return _collect_multicast_results(
        units, tasks, timeout
    )  # add a timeout so that we don't hold up a thread forever.
