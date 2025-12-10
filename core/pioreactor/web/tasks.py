# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import grp
import json
import logging
import os
import pwd
import shutil
import stat
import zipfile
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

from msgspec import DecodeError
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


def _process_delayed_json_response(unit: str, response: Response) -> tuple[str, Any]:
    """
    Handle delayed HTTP responses (202 with result_url_path) and immediate 200 responses.
    Returns the unit and the appropriate JSON data or result value.
    """
    data = response.json()
    if response.status_code == 202 and "result_url_path" in data:
        sleep(0.1)
        return _get_from_unit(unit, data["result_url_path"])
    if response.status_code == 200:
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
    result = run((PIO_EXECUTABLE,) + args, env=env)
    return result.returncode == 0


@huey.task()
def pio_plugins_list(*args: str, env: dict[str, str] | None = None) -> tuple[bool, str]:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio",) + args)}`, {env=}')
    result = run((PIO_EXECUTABLE,) + args, capture_output=True, text=True, env=env)
    return result.returncode == 0, result.stdout.strip()


@huey.task()
@huey.lock_task("export-data-lock")
def pio_run_export_experiment_data(*args: str, env: dict[str, str] | None = None) -> tuple[bool, str]:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio", "run", "export_experiment_data") + args)}`, {env=}')
    result = run(
        (PIO_EXECUTABLE, "run", "export_experiment_data") + args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode == 0, result.stdout.strip()


@huey.task(priority=100)
def pio_kill(*args: str, env: dict[str, str] | None = None) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio", "kill") + args)}`, {env=}')
    result = run((PIO_EXECUTABLE, "kill") + args, env=env)
    return result.returncode == 0


@huey.task()
@huey.lock_task("plugins-lock")
def pio_plugins(*args: str, env: dict[str, str] | None = None) -> bool:
    # install / uninstall only
    env = filter_to_allowed_env(env or {})
    assert args[0] in ("install", "uninstall")
    logger.debug(f'Executing `{join(("pio", "plugins") + args)}`, {env=}')
    result = run((PIO_EXECUTABLE, "plugins") + args, env=env)
    return result.returncode == 0


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
    backup_dir = Path("/tmp") / f"{hostname}_dot_pioreactor_backup_{current_utc_timestamp()}"

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


@huey.task(priority=50)
def multicast_post(
    endpoint: str,
    units: list[str],
    json: dict | list[dict | None] | None = None,
    params: dict | list[dict | None] | None = None,
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    if not isinstance(json, list):
        json = [json] * len(units)

    assert json is not None

    if not isinstance(params, list):
        params = [params] * len(units)

    tasks = post_into_unit.map(((units[i], endpoint, json[i], params[i]) for i in range(len(units))))

    return {
        unit: response for (unit, response) in tasks.get(blocking=True, timeout=30)
    }  # add a timeout so that we don't hold up a thread forever.


@huey.task(priority=10)
def get_from_unit(
    unit: str, endpoint: str, json: dict | None = None, timeout=5.0, return_raw=False
) -> tuple[str, Any]:
    return _get_from_unit(unit, endpoint, json=json, timeout=timeout, return_raw=return_raw)


def _get_from_unit(
    unit: str, endpoint: str, json: dict | None = None, timeout=5.0, return_raw=False
) -> tuple[str, Any]:
    try:
        address = resolve_to_address(unit)

        r = get_from(address, endpoint, json=json, timeout=timeout)
        r.raise_for_status()

        if return_raw:
            return unit, r.content or None

        # delayed or immediate JSON response
        return _process_delayed_json_response(unit, r)

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
    unsorted_responses = {
        unit: response for (unit, response) in tasks.get(blocking=True, timeout=15)
    }  # add a timeout so that we don't hold up a thread forever.

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
def multicast_patch(endpoint: str, units: list[str], json: dict | None = None) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    tasks = patch_into_unit.map(((unit, endpoint, json) for unit in units))

    return {
        unit: response for (unit, response) in tasks.get(blocking=True, timeout=30)
    }  # add a timeout so that we don't hold up a thread forever.


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
def multicast_delete(endpoint: str, units: list[str], json: dict | None = None) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    tasks = delete_from_unit.map(((unit, endpoint, json) for unit in units))

    return {
        unit: response for (unit, response) in tasks.get(blocking=True, timeout=30)
    }  # add a timeout so that we don't hold up a thread forever.
