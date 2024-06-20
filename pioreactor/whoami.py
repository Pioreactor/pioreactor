# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import time
import warnings
from functools import cache

from pioreactor import mureq
from pioreactor.exc import NotAssignedAnExperimentError
from pioreactor.exc import NoWorkerFoundError
from pioreactor.version import serial_number
from pioreactor.version import version_text_to_tuple


UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


def get_testing_experiment_name() -> str:
    try:
        exp = get_assigned_experiment_name(get_unit_name())
        return f"_testing_{exp}"
    except NotAssignedAnExperimentError:
        return f"_testing_{NO_EXPERIMENT}"


def get_latest_experiment_name() -> str:
    warnings.warn("Use whoami.get_assigned_experiment_name(unit) instead", DeprecationWarning, stacklevel=2)
    return get_assigned_experiment_name(get_unit_name())


def get_assigned_experiment_name(unit_name: str) -> str:
    return _get_assigned_experiment_name(unit_name)


def _get_assigned_experiment_name(unit_name: str) -> str:
    from pioreactor.pubsub import get_from_leader
    from pioreactor.logging import create_logger

    if os.environ.get("EXPERIMENT") is not None:
        return os.environ["EXPERIMENT"]
    elif is_testing_env():
        return "_testing_experiment"

    from pioreactor.config import leader_address

    retries = 6
    exit_reason = None

    for attempt in range(retries):
        try:
            result = get_from_leader(f"/api/workers/{unit_name}/experiment")
            result.raise_for_status()
            data = result.json()
            return data["experiment"]
        except mureq.HTTPErrorStatus as e:
            if e.status_code == 401:
                # auth error, something is wrong
                exit_reason = "auth"
                break
            elif e.status_code == 404:
                raise NotAssignedAnExperimentError(f"Worker {unit_name} is not assigned to an experiment")
        except mureq.HTTPException:
            exit_reason = "connection_refused"
        except Exception:
            # some other error? Keep trying
            pass
        time.sleep(0.5 * attempt)
    else:
        exit_reason = "timeout"

    logger = create_logger("pioreactor", experiment=UNIVERSAL_EXPERIMENT, to_mqtt=False)

    if exit_reason == "auth":
        logger.warning(
            f"Error in authentication to UI. Check http://{leader_address} and config.ini for api_key."
        )
    elif exit_reason == "timeout":
        logger.warning(f"Not able to access experiments in UI. Check http://{leader_address}/api/experiments")
    elif exit_reason == "connection_refused":
        logger.warning(
            f"Not able to access experiments in UI. Check http://{leader_address} is online and check network."
        )
    return NO_EXPERIMENT


def is_active(unit_name: str) -> bool:
    from pioreactor.pubsub import get_from_leader

    if os.environ.get("ACTIVE") == "1":
        return True
    elif os.environ.get("ACTIVE") == "0":
        return False

    if is_testing_env():
        return True

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
    return ("pytest" in sys.modules) or (os.environ.get("TESTING") is not None)


def get_hostname() -> str:
    import socket

    if os.environ.get("HOSTNAME"):
        return os.environ["HOSTNAME"]
    elif is_testing_env():
        return "testing_unit"
    else:
        return socket.gethostname()


@cache
def get_unit_name() -> str:
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


def am_I_active_worker() -> bool:
    return is_active(get_unit_name())


@cache
def get_hashed_serial_number() -> str:
    from hashlib import md5

    return md5(serial_number.encode()).hexdigest()


@cache
def get_pioreactor_version() -> tuple[int, int]:
    if os.environ.get("PIO_VERSION"):
        return version_text_to_tuple(os.environ["PIO_VERSION"])

    from pioreactor.config import config

    return version_text_to_tuple(config.get("pioreactor", "version", fallback="1.0"))  # type: ignore


@cache
def get_pioreactor_model() -> str:
    from pioreactor.config import config

    return config.get("pioreactor", "model")


def get_pioreactor_model_and_version() -> str:
    return f"{get_pioreactor_model()} v{'.'.join(map(str, get_pioreactor_version()))}"


def get_image_git_hash() -> str:
    try:
        with open("/home/pioreactor/.pioreactor/.image_info") as f:
            return f.read().strip().split("=")[1]
    except OSError:  # catch FileNotFoundError, PermissionError, and other file-related exceptions
        return "<Failed to fetch>"


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
