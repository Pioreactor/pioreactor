# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import time
from functools import cache
from typing import TYPE_CHECKING

from pioreactor.exc import NoModelAssignedError
from pioreactor.exc import NotAssignedAnExperimentError
from pioreactor.exc import NoWorkerFoundError
from pioreactor.exc import UnknownModelAssignedError

if TYPE_CHECKING:
    from pioreactor import types as pt
    from pioreactor.structs import Model


UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


def get_testing_experiment_name() -> "pt.Experiment":
    try:
        exp = get_assigned_experiment_name(get_unit_name())
        return f"_testing_{exp}"
    except NotAssignedAnExperimentError:
        return f"_testing_{NO_EXPERIMENT}"


def get_assigned_experiment_name(unit_name: "pt.Unit") -> "pt.Experiment":
    return _get_assigned_experiment_name(unit_name)


def _get_assigned_experiment_name(unit_name: "pt.Unit") -> "pt.Experiment":

    if os.environ.get("EXPERIMENT") is not None:
        return os.environ["EXPERIMENT"]
    elif is_testing_env():
        return "_testing_experiment"

    from pioreactor.pubsub import get_from_leader
    from pioreactor.config import leader_address
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.mureq import HTTPException

    retries = 6

    for attempt in range(retries):
        try:
            result = get_from_leader(f"/api/workers/{unit_name}/experiment")
            result.raise_for_status()
            data = result.json()
            return data["experiment"]
        except HTTPErrorStatus as e:
            if e.status_code == 401:
                # auth error, something is wrong
                raise HTTPException(
                    f"Error in authentication to UI. Check http://{leader_address} and config.ini for api_key."
                )
            elif e.status_code == 404:
                data = result.json()
                raise NotAssignedAnExperimentError(data["error"])
        except HTTPException:
            # connection errors are often transient (e.g. the leader's web server restarting), so retry.
            if attempt == retries - 1:
                raise HTTPException(
                    f"Not able to access experiments in UI. Check http://{leader_address} is online and check network."
                )
        except Exception:
            # some other error? Keep trying
            pass
        time.sleep(0.5 * attempt)
    else:
        raise ConnectionError(
            f"Not able to access experiments in UI. Check http://{leader_address}/api/experiments."
        )


def is_active(unit_name: "pt.Unit") -> bool:
    return _is_active(unit_name)


def _is_active(unit_name: "pt.Unit") -> bool:
    if os.environ.get("ACTIVE") == "1" or is_testing_env():
        return True
    elif os.environ.get("ACTIVE") == "0":
        return False

    from pioreactor.pubsub import get_from_leader
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.mureq import HTTPException

    try:
        result = get_from_leader(f"/api/workers/{unit_name}")
        result.raise_for_status()
        data = result.json()
        return bool(data["is_active"])
    except HTTPErrorStatus as e:
        if e.status_code == 404:
            raise NoWorkerFoundError(f"Worker {unit_name} is not present in leader's inventory")
        else:
            raise e
    except HTTPException as e:
        raise e


def is_testing_env() -> bool:
    return ("pytest" in sys.modules) or (os.environ.get("TESTING", "") == "1")


def get_hostname() -> str:
    import socket

    if os.environ.get("HOSTNAME"):
        return os.environ["HOSTNAME"]
    elif is_testing_env():
        from pioreactor.config import leader_hostname

        return leader_hostname
    else:
        return socket.gethostname()


def get_unit_name() -> "pt.Unit":
    hostname = get_hostname()

    if hostname == "raspberrypi":
        raise ValueError("Did you forget to set the hostname?")
    else:
        return hostname


@cache
def am_I_leader() -> bool:
    if is_testing_env():
        return True

    from pioreactor.config import leader_hostname

    return get_unit_name() == leader_hostname


@cache
def am_I_a_worker() -> bool:
    if is_testing_env():
        return True

    from pioreactor.pubsub import get_from_leader
    from pioreactor.mureq import HTTPErrorStatus

    try:
        result = get_from_leader(f"/api/workers/{get_unit_name()}")
        result.raise_for_status()
        return True
    except HTTPErrorStatus as e:
        if e.status_code == 404:
            return False
        else:
            raise e


def get_pioreactor_model(unit_name: pt.Unit | None = None) -> Model:
    """
    Return the Pioreactor model for a specific unit. Defaults to the local unit.
    """
    from pioreactor.models import get_registered_models

    target_unit_name = unit_name or get_unit_name()

    name, version = _get_pioreactor_model_name_and_version(target_unit_name)

    if name is None or version is None:
        raise NoModelAssignedError("Unknown Pioreactor model: name and version not set yet.")

    try:
        return get_registered_models()[(name, version)]
    except KeyError:
        raise UnknownModelAssignedError(f"Unknown Pioreactor model {name} v{version}.")


def _get_pioreactor_model_name_and_version(unit_name: "pt.Unit") -> tuple[str | None, str | None]:
    # The local unit's model can be provided by env (jobs launched from the UI/profiles set these).
    name: str | None = None
    version: str | None = None

    if unit_name == get_unit_name():
        name = os.environ.get("MODEL_NAME") or None
        version = os.environ.get("MODEL_VERSION") or None
        if name is None and is_testing_env():
            name = "pioreactor_40ml"

    if name is not None and version is not None:
        return name, version

    leader_name, leader_version = _get_pioreactor_model_name_and_version_from_leader(unit_name)
    return name or leader_name, version or leader_version


# Model lookups are hot (safety thresholds, bioreactor validation on every dosing event), and
# a worker's model changes rarely, so we briefly cache complete answers from the leader.
_MODEL_FROM_LEADER_TTL_SECONDS = 30.0
_model_from_leader_cache: dict[str, tuple[float, str, str]] = {}


def _get_pioreactor_model_name_and_version_from_leader(
    unit_name: "pt.Unit",
) -> tuple[str | None, str | None]:
    use_cache = not is_testing_env()

    if use_cache and (cached := _model_from_leader_cache.get(unit_name)) is not None:
        cached_at, cached_name, cached_version = cached
        if time.monotonic() - cached_at < _MODEL_FROM_LEADER_TTL_SECONDS:
            return cached_name, cached_version

    from pioreactor.pubsub import get_from_leader
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.mureq import HTTPException

    try:
        result = get_from_leader(f"/api/workers/{unit_name}")
        result.raise_for_status()
        data = result.json()
    except HTTPErrorStatus as e:
        if e.status_code == 404:
            raise NoWorkerFoundError(f"Worker {unit_name} is not found or not assigned a model.")
        raise e
    except HTTPException as e:
        raise e

    name, version = data["model_name"], data["model_version"]

    if use_cache and name is not None and version is not None:
        # only cache complete answers, so a newly assigned model is picked up immediately.
        _model_from_leader_cache[unit_name] = (time.monotonic(), name, version)

    return name, version


def clear_pioreactor_model_cache() -> None:
    _model_from_leader_cache.clear()


@cache
def get_image_git_hash() -> str:
    try:
        with open("/home/pioreactor/.pioreactor/.image_info") as f:
            return f.read().strip().split("=")[1]
    except OSError:  # catch FileNotFoundError, PermissionError, and other file-related exceptions
        return "<Failed to fetch>"


@cache
def check_firstboot_successful() -> bool:
    if is_testing_env():
        return True
    return not os.path.isfile("/usr/local/bin/firstboot.sh")
