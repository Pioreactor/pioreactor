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


def _remember_membership(unit: str, experiment: str | None = None, is_active: bool | None = None) -> None:
    """Persist this unit's last known membership. Remote units' membership stays leader-only."""
    if unit != get_unit_name():
        return

    # Lazy imports avoid the config/utils -> whoami import cycle.
    from pioreactor.utils import local_persistent_storage
    from pioreactor.utils.timing import current_utc_timestamp

    updated_at = current_utc_timestamp()
    with local_persistent_storage("cluster_membership") as storage:
        for field, value in (("experiment", experiment), ("is_active", is_active)):
            if value is not None:
                storage[field] = value
                storage[f"{field}_updated_at"] = updated_at


def _forget_membership(unit: str) -> None:
    if unit != get_unit_name():
        return

    from pioreactor.utils import local_persistent_storage

    with local_persistent_storage("cluster_membership") as storage:
        storage.empty()


def _last_known_membership(unit: str, field: str) -> str | bool | None:
    """Only use after a local-unit transport failure; HTTP responses remain authoritative."""
    if unit != get_unit_name():
        return None

    from pioreactor.logging import create_logger
    from pioreactor.utils import local_persistent_storage

    with local_persistent_storage("cluster_membership") as storage:
        if field not in storage:
            return None
        value = storage.getboolean(field) if field == "is_active" else str(storage[field])
        updated_at = storage.get(f"{field}_updated_at")
    # Logging must neither look up the assignment again nor connect to the leader.
    create_logger("whoami", unit=unit, experiment=UNIVERSAL_EXPERIMENT, to_mqtt=False).warning(
        f"Leader unreachable, using last known {field} {value!r} for {unit} from {updated_at}."
    )
    return value


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
            experiment = data["experiment"]
            _remember_membership(unit_name, experiment=experiment, is_active=bool(data["is_active"]))
            return experiment
        except HTTPErrorStatus as e:
            if e.status_code == 401:
                # auth error, something is wrong
                raise HTTPException(
                    f"Error in authentication to UI. Check http://{leader_address} and config.ini for api_key."
                )
            elif e.status_code == 404:
                _forget_membership(unit_name)
                data = result.json()
                raise NotAssignedAnExperimentError(data["error"])
        except HTTPException:
            # connection errors are often transient (e.g. the leader's web server restarting), so retry.
            if attempt == retries - 1:
                last_experiment = _last_known_membership(unit_name, "experiment")
                if isinstance(last_experiment, str):
                    return last_experiment
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
        active = bool(data["is_active"])
        _remember_membership(unit_name, is_active=active)
        return active
    except HTTPErrorStatus as e:
        if e.status_code == 404:
            _forget_membership(unit_name)
            raise NoWorkerFoundError(f"Worker {unit_name} is not present in leader's inventory")
        else:
            raise e
    except HTTPException:
        last_active = _last_known_membership(unit_name, "is_active")
        if isinstance(last_active, bool):
            return last_active
        raise


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
    # Lazy import avoids the config/utils -> whoami import cycle.
    from pioreactor.unit_model import get_local_model
    from pioreactor.unit_model import save_local_model

    is_local_unit = unit_name == get_unit_name()

    # Each unit owns its model.
    if is_local_unit and (local := get_local_model()) is not None:
        return local

    # Development and CI environments set the model in the environment.
    name: str | None = None
    version: str | None = None

    if is_local_unit:
        name = os.environ.get("MODEL_NAME") or None
        version = os.environ.get("MODEL_VERSION") or None
        if name is None and is_testing_env():
            name = "pioreactor_40ml"

    if name is not None and version is not None:
        return name, version

    leader_name, leader_version = _get_pioreactor_model_name_and_version_from_leader(unit_name)
    if is_local_unit and leader_name is not None and leader_version is not None:
        # A unit upgraded from before it stored its model adopts the leader's record once.
        return save_local_model(leader_name, leader_version, only_if_unset=True)
    return name or leader_name, version or leader_version


def _get_pioreactor_model_name_and_version_from_leader(
    unit_name: "pt.Unit",
) -> tuple[str | None, str | None]:
    from pioreactor.pubsub import get_from_leader
    from pioreactor.mureq import HTTPErrorStatus

    try:
        result = get_from_leader(f"/api/workers/{unit_name}")
        result.raise_for_status()
    except HTTPErrorStatus as e:
        if e.status_code == 404:
            raise NoWorkerFoundError(f"Worker {unit_name} is not found or not assigned a model.")
        raise

    data = result.json()
    return data["model_name"], data["model_version"]


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
