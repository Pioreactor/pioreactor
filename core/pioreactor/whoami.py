# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import time
import warnings
from functools import cache
from typing import TYPE_CHECKING

from pioreactor import mureq
from pioreactor.exc import NotAssignedAnExperimentError
from pioreactor.exc import NoWorkerFoundError

if TYPE_CHECKING:
    from pioreactor import types as pt
    from pioreactor.structs import Model


UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


def get_latest_experiment_name() -> pt.Experiment:
    warnings.warn("Use whoami.get_assigned_experiment_name(unit) instead", DeprecationWarning, stacklevel=2)
    return get_assigned_experiment_name(get_unit_name())


def get_testing_experiment_name() -> pt.Experiment:
    try:
        exp = get_assigned_experiment_name(get_unit_name())
        return f"_testing_{exp}"
    except NotAssignedAnExperimentError:
        return f"_testing_{NO_EXPERIMENT}"


def get_assigned_experiment_name(unit_name: pt.Unit) -> pt.Experiment:
    return _get_assigned_experiment_name(unit_name)


def _get_assigned_experiment_name(unit_name: pt.Unit) -> pt.Experiment:
    from pioreactor.pubsub import get_from_leader
    from pioreactor.config import leader_address

    if os.environ.get("EXPERIMENT") is not None:
        return os.environ["EXPERIMENT"]
    elif is_testing_env():
        return "_testing_experiment"

    retries = 6

    for attempt in range(retries):
        try:
            result = get_from_leader(f"/api/workers/{unit_name}/experiment")
            result.raise_for_status()
            data = result.json()
            return data["experiment"]
        except mureq.HTTPErrorStatus as e:
            if e.status_code == 401:
                # auth error, something is wrong
                raise mureq.HTTPException(
                    f"Error in authentication to UI. Check http://{leader_address} and config.ini for api_key."
                )
            elif e.status_code == 404:
                data = result.json()
                raise NotAssignedAnExperimentError(data["error"])
        except mureq.HTTPException:
            raise mureq.HTTPException(
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


def is_active(unit_name: pt.Unit) -> bool:
    if os.environ.get("ACTIVE") == "1" or is_testing_env():
        return True
    elif os.environ.get("ACTIVE") == "0":
        return False

    from pioreactor.pubsub import get_from_leader

    try:
        result = get_from_leader(f"/api/workers/{unit_name}")
        result.raise_for_status()
        data = result.json()
        return bool(data["is_active"])
    except mureq.HTTPErrorStatus as e:
        if e.status_code == 404:
            raise NoWorkerFoundError(f"Worker {unit_name} is not present in leader's inventory")
        else:
            raise e
    except mureq.HTTPException as e:
        raise e


@cache
def is_testing_env() -> bool:
    return ("pytest" in sys.modules) or (os.environ.get("TESTING", "") == "1")


@cache
def get_hostname() -> str:
    import socket

    if os.environ.get("HOSTNAME"):
        return os.environ["HOSTNAME"]
    elif is_testing_env():
        return "testing_unit"
    else:
        return socket.gethostname()


@cache
def get_unit_name() -> pt.Unit:
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
    from pioreactor.pubsub import get_from_leader

    if is_testing_env():
        return True

    try:
        result = get_from_leader(f"/api/workers/{get_unit_name()}")
        result.raise_for_status()
        return True
    except mureq.HTTPErrorStatus as e:
        if e.status_code == 404:
            return False
        else:
            raise e


@cache
def get_pioreactor_model() -> Model:
    """Return the Model struct for this Pioreactor (by env/EERPOM/HARDWARE env).
    Falls back to the 20ml v1.0 factory default if unrecognized.
    """
    from pioreactor.models import get_registered_models

    name = _get_pioreactor_model_name()
    version = _get_pioreactor_model_version()
    try:
        return get_registered_models()[(name, version)]
    except KeyError:
        raise ValueError(f"Unknown Pioreactor model {name} v{version}.")


def _get_pioreactor_model_version() -> str:
    # pioreactor model version
    if os.environ.get("MODEL_VERSION"):
        return os.environ["MODEL_VERSION"]

    from pioreactor.pubsub import get_from_leader

    try:
        result = get_from_leader(f"/api/workers/{get_unit_name()}")
        result.raise_for_status()
        data = result.json()
        return data["model_version"]
    except mureq.HTTPErrorStatus as e:
        if e.status_code == 404:
            raise NoWorkerFoundError(f"Worker {get_unit_name()} is not present in leader's inventory")
        else:
            raise e
    except mureq.HTTPException as e:
        raise e


def _get_pioreactor_model_name() -> str:
    # pioreactor model name
    if os.environ.get("MODEL_NAME"):
        return os.environ["MODEL_NAME"]
    elif is_testing_env():
        return "pioreactor_40ml"

    from pioreactor.pubsub import get_from_leader

    try:
        result = get_from_leader(f"/api/workers/{get_unit_name()}")
        result.raise_for_status()
        data = result.json()
        return data["model_name"]
    except mureq.HTTPErrorStatus as e:
        if e.status_code == 404:
            raise NoWorkerFoundError(f"Worker {get_unit_name()} is not present in leader's inventory")
        else:
            raise e
    except mureq.HTTPException as e:
        raise e


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
    return os.path.isfile("/usr/local/bin/firstboot.sh.done")


if is_testing_env():
    # allow Blinka to think we are an Rpi:
    # https://github.com/adafruit/Adafruit_Python_PlatformDetect/blob/75f69806222fbaf8535130ed2eacd07b06b1a298/adafruit_platformdetect/board.py
    os.environ["BLINKA_FORCECHIP"] = "BCM2XXX"  # RaspberryPi
    os.environ["BLINKA_FORCEBOARD"] = "RASPBERRY_PI_3A_PLUS"  # Raspberry Pi 3 Model A Plus Rev 1.0
    os.environ["FIRMWARE"] = "1.0"
    os.environ["HARDWARE"] = "1.2"
    os.environ["MODEL_NAME"] = "pioreactor_40ml"
    os.environ["MODEL_VERSION"] = "1.0"
