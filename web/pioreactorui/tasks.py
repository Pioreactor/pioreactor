# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from shlex import join
from subprocess import check_call
from subprocess import DEVNULL
from subprocess import Popen
from subprocess import run
from subprocess import TimeoutExpired
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

from .config import CACHE_DIR
from .config import huey
from .config import is_testing_env


logger = create_logger(
    "huey.consumer",
    source="huey",
    experiment="$experiment",
    log_file_location=pioreactor_config["logging"]["ui_log_file"],
)

if not is_testing_env():
    PIO_EXECUTABLE = "/usr/local/bin/pio"
    PIOS_EXECUTABLE = "/usr/local/bin/pios"
else:
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


def filter_to_allowed_env(env: dict):
    """
    Filter the environment dictionary to only include allowed keys.
    This is used to prevent passing sensitive or unnecessary environment variables.
    """
    return {k: v for k, v in env.items() if k in ALLOWED_ENV and v is not None and v != "" and v != "None"}


def _process_delayed_json_response(worker: str, response: Response) -> tuple[str, Any]:
    """
    Handle delayed HTTP responses (202 with result_url_path) and immediate 200 responses.
    Returns the worker and the appropriate JSON data or result value.
    """
    data = response.json()
    if response.status_code == 202 and "result_url_path" in data:
        sleep(0.1)
        return _get_from_worker(worker, data["result_url_path"])
    if response.status_code == 200:
        if "task_id" in data:
            return worker, data["result"]
        else:
            return worker, data
    return worker, None


@huey.on_startup()
def initialized():
    logger.debug("Starting Huey consumer...")
    logger.debug(f"Cache directory = {CACHE_DIR}")


@huey.task()
def pio_run(
    *args: str,
    env: dict[str, str] | None = None,
    config_overrides: tuple[str, ...] = (),
    grace_s: float = 0.5,  # how long to watch for "fast-fail"
) -> bool:
    command = (PIO_EXECUTABLE, "run") + config_overrides + args

    env = {k: v for k, v in (env or {}).items() if k in ALLOWED_ENV}

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
        logger.exception("Failed to spawn %r", command)
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

    logger.debug("Updating app and ui on workers")
    update_app_across_all_workers = [PIOS_EXECUTABLE, "update", "-y"]
    run(update_app_across_all_workers)
    return True


@huey.task()
def update_app_from_release_archive_across_cluster(archive_location: str, units: str) -> bool:
    if units == "$broadcast":
        logger.debug(f"Updating app on leader from {archive_location}")
        update_app_on_leader = ["pio", "update", "app", "--source", archive_location]
        check_call(update_app_on_leader)

        logger.debug(f"Updating app and ui on workers from {archive_location}")
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

        if not whoami.am_I_a_worker():
            # update the UI on the leader
            update_ui_on_leader = [
                "pio",
                "update",
                "ui",
                "--source",
                "/tmp/pioreactorui_archive.tar.gz",
            ]
            run(update_ui_on_leader)

        return True
    else:
        logger.debug(f"Updating app and ui on unit {units} from {archive_location}")
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
def pio(*args: str, env: dict[str, str] = {}) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio",) + args)}`, {env=}')
    result = run((PIO_EXECUTABLE,) + args, env=env)
    return result.returncode == 0


@huey.task()
def pio_plugins_list(*args: str, env: dict[str, str] = {}) -> tuple[bool, str]:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio",) + args)}`, {env=}')
    result = run((PIO_EXECUTABLE,) + args, capture_output=True, text=True, env=env)
    return result.returncode == 0, result.stdout.strip()


@huey.task()
@huey.lock_task("export-data-lock")
def pio_run_export_experiment_data(*args: str, env: dict[str, str] = {}) -> tuple[bool, str]:
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
def pio_kill(*args: str, env: dict[str, str] = {}) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio", "kill") + args)}`, {env=}')
    result = run((PIO_EXECUTABLE, "kill") + args, env=env)
    return result.returncode == 0


@huey.task()
@huey.lock_task("plugins-lock")
def pio_plugins(*args: str, env: dict[str, str] = {}) -> bool:
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
    # iso8601 format
    if whoami.is_testing_env():
        return True
    r = run(["sudo", "chronyc", "-a", "makestep"])
    return r.returncode == 0


@huey.task()
@huey.lock_task("update-lock")
def pio_update_app(*args: str, env: dict[str, str] = {}) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio", "update", "app") + args)}`, {env=}')
    result = run((PIO_EXECUTABLE, "update", "app") + args, env=env)
    return result.returncode == 0


@huey.task()
@huey.lock_task("update-lock")
def pio_update(*args: str, env: dict[str, str] = {}) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio", "update") + args)}`, {env=}')
    run((PIO_EXECUTABLE, "update") + args, env=env)
    # HACK: this always returns >0 because it kills huey, I think, so just return true
    return True


@huey.task()
@huey.lock_task("update-lock")
def pio_update_ui(*args: str, env: dict[str, str] = {}) -> bool:
    env = filter_to_allowed_env(env or {})
    logger.debug(f'Executing `{join(("pio", "update", "ui") + args)}`, {env=}')
    run((PIO_EXECUTABLE, "update", "ui") + args, env=env)
    # this always returns >0 because it kills huey, I think, so just return true
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
def reboot() -> bool:
    logger.debug("Rebooting now")
    if whoami.is_testing_env():
        return True
    result = run(["sudo", "reboot"])
    return result.returncode == 0


@huey.task()
def pios(*args: str, env: dict[str, str] = {}) -> bool:
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
        logger.error(e)
        return False


@huey.task()
def write_config_and_sync(
    config_path: str, text: str, units: str, flags: str, env: dict[str, str] = {}
) -> tuple[bool, str]:
    env = filter_to_allowed_env(env or {})
    try:
        with open(config_path, "w") as f:
            f.write(text)

        logger.debug(
            f'Executing `{join((PIOS_EXECUTABLE, "sync-configs", "--units", units, flags))}`, {env=}'
        )

        result = run(
            (PIOS_EXECUTABLE, "sync-configs", "--units", units, flags),
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        if result.returncode != 0:
            raise Exception(result.stderr.strip())

        return (True, "")

    except Exception as e:
        logger.error(str(e))
        return (False, "Could not sync configs to all Pioreactors.")


@huey.task(priority=10)
def post_into_worker(
    worker: str, endpoint: str, json: dict | None = None, params: dict | None = None
) -> tuple[str, Any]:
    try:
        address = resolve_to_address(worker)
        r = post_into(address, endpoint, json=json, params=params, timeout=1)
        r.raise_for_status()

        if r.content is None:
            return worker, None

        # delayed or immediate JSON response
        return _process_delayed_json_response(worker, r)

    except (HTTPErrorStatus, HTTPException) as e:
        logger.error(
            f"Could not post to {worker}'s {address=}/{endpoint=}, sent {json=} and returned {e}. Check connection? Check port?"
        )
        return worker, None
    except DecodeError:
        logger.error(
            f"Could not decode response from {worker}'s {endpoint=}, sent {json=} and returned {r.body.decode()}."
        )
        return worker, None


@huey.task(priority=5)
def multicast_post_across_cluster(
    endpoint: str,
    workers: list[str],
    json: dict | list[dict | None] | None = None,
    params: dict | list[dict | None] | None = None,
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    if not isinstance(json, list):
        json = [json] * len(workers)

    assert json is not None

    if not isinstance(params, list):
        params = [params] * len(workers)

    tasks = post_into_worker.map(((workers[i], endpoint, json[i], params[i]) for i in range(len(workers))))

    return {
        worker: response for (worker, response) in tasks.get(blocking=True, timeout=30)
    }  # add a timeout so that we don't hold up a thread forever.


@huey.task(priority=10)
def get_from_worker(
    worker: str, endpoint: str, json: dict | None = None, timeout=5.0, return_raw=False
) -> tuple[str, Any]:
    return _get_from_worker(worker, endpoint, json=json, timeout=timeout, return_raw=return_raw)


def _get_from_worker(
    worker: str, endpoint: str, json: dict | None = None, timeout=5.0, return_raw=False
) -> tuple[str, Any]:
    try:
        address = resolve_to_address(worker)

        r = get_from(address, endpoint, json=json, timeout=timeout)
        r.raise_for_status()

        if return_raw:
            return worker, r.content or None

        # delayed or immediate JSON response
        return _process_delayed_json_response(worker, r)

    except (HTTPErrorStatus, HTTPException) as e:
        logger.error(
            f"Could not get from {worker}'s {address=}, {endpoint=}, sent {json=} and returned {e}. Check connection? Check port?"
        )
        return worker, None
    except DecodeError:
        logger.error(
            f"Could not decode response from {worker}'s {endpoint=}, sent {json=} and returned {r.body.decode()}."
        )
        return worker, None


@huey.task(priority=5)
def multicast_get_across_cluster(
    endpoint: str,
    workers: list[str],
    json: dict | list[dict | None] | None = None,
    timeout: float = 5.0,
    return_raw=False,
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    if not isinstance(json, list):
        json = [json] * len(workers)

    tasks = get_from_worker.map(
        ((workers[i], endpoint, json[i], timeout, return_raw) for i in range(len(workers)))
    )
    unsorted_responses = {
        worker: response for (worker, response) in tasks.get(blocking=True, timeout=15)
    }  # add a timeout so that we don't hold up a thread forever.

    return dict(sorted(unsorted_responses.items()))  # always sort alphabetically for downstream uses.


@huey.task(priority=10)
def patch_into_worker(worker: str, endpoint: str, json: dict | None = None) -> tuple[str, Any]:
    try:
        address = resolve_to_address(worker)
        r = patch_into(address, endpoint, json=json, timeout=1)
        r.raise_for_status()

        if r.content is None:
            return worker, None

        # delayed or immediate JSON response
        return _process_delayed_json_response(worker, r)

    except (HTTPErrorStatus, HTTPException) as e:
        logger.error(
            f"Could not PATCH to {worker}'s {address=}/{endpoint=}, sent {json=} and returned {e}. Check connection? Check port?"
        )
        return worker, None
    except DecodeError:
        logger.error(
            f"Could not decode response from {worker}'s {endpoint=}, sent {json=} and returned {r.body.decode()}."
        )
        return worker, None


@huey.task(priority=5)
def multicast_patch_across_cluster(
    endpoint: str, workers: list[str], json: dict | None = None
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    tasks = patch_into_worker.map(((worker, endpoint, json) for worker in workers))

    return {
        worker: response for (worker, response) in tasks.get(blocking=True, timeout=30)
    }  # add a timeout so that we don't hold up a thread forever.


@huey.task(priority=10)
def delete_from_worker(worker: str, endpoint: str, json: dict | None = None) -> tuple[str, Any]:
    try:
        r = delete_from(resolve_to_address(worker), endpoint, json=json, timeout=1)
        r.raise_for_status()
        return worker, r.json() if r.content else None
    except (HTTPErrorStatus, HTTPException) as e:
        logger.error(
            f"Could not DELETE {worker}'s {endpoint=}, sent {json=} and returned {e}. Check connection?"
        )
        return worker, None
    except DecodeError:
        logger.error(
            f"Could not decode response from {worker}'s {endpoint=}, sent {json=} and returned {r.body.decode()}."
        )
        return worker, None


@huey.task(priority=5)
def multicast_delete_across_cluster(
    endpoint: str, workers: list[str], json: dict | None = None
) -> dict[str, Any]:
    # this function "consumes" one huey thread waiting fyi
    assert endpoint.startswith("/unit_api")

    tasks = delete_from_worker.map(((worker, endpoint, json) for worker in workers))

    return {
        worker: response for (worker, response) in tasks.get(blocking=True, timeout=30)
    }  # add a timeout so that we don't hold up a thread forever.
