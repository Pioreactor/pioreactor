# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import time
from functools import cache
from hashlib import md5

from msgspec.json import decode

from pioreactor.mureq import get
from pioreactor.structs import ExperimentMetadata
from pioreactor.version import serial_number

UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


def get_latest_testing_experiment_name() -> str:
    exp = get_latest_experiment_name()
    return f"_testing_{exp}"


@cache
def get_latest_experiment_name() -> str:
    return _get_latest_experiment_name()


def _get_latest_experiment_name() -> str:
    if os.environ.get("EXPERIMENT") is not None:
        return os.environ["EXPERIMENT"]
    elif is_testing_env():
        return "_testing_experiment"

    from pioreactor.config import leader_address

    retries = 10
    for attempt in range(retries):
        try:
            result = get(f"http://{leader_address}/api/experiments/latest")
            result.raise_for_status()
            return decode(result.body, type=ExperimentMetadata).experiment
        except Exception:
            time.sleep(0.5 * attempt)

    from pioreactor.logging import create_logger

    logger = create_logger("pioreactor", experiment=UNIVERSAL_EXPERIMENT, to_mqtt=False)
    logger.warning(
        f"No experiment found. Check http://{leader_address}/api/experiments/latest for an experiment."
    )
    return NO_EXPERIMENT


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


@cache
def am_I_active_worker() -> bool:
    if is_testing_env():
        return True

    from pioreactor.config import get_active_workers_in_inventory

    return get_unit_name() in get_active_workers_in_inventory()


@cache
def get_hashed_serial_number() -> str:
    return md5(serial_number.encode()).hexdigest()


def get_rpi_machine() -> str:
    if not is_testing_env():
        with open("/proc/device-tree/model") as f:
            return f.read().strip()
    else:
        return "Raspberry Pi 3 - testing"


def get_image_git_hash() -> str:
    try:
        with open("/home/pioreactor/.pioreactor/.image_info") as f:
            return f.read().strip().split("=")[1]
    except OSError:  # catch FileNotFoundError, PermissionError, and other file-related exceptions
        return "<Failed to fetch>"


if is_testing_env():
    import fake_rpi  # type: ignore

    fake_rpi.toggle_print(False)
    sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
    sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO

    # allow Blinka to think we are an Rpi:
    # https://github.com/adafruit/Adafruit_Python_PlatformDetect/blob/75f69806222fbaf8535130ed2eacd07b06b1a298/adafruit_platformdetect/board.py
    os.environ["BLINKA_FORCECHIP"] = "BCM2XXX"  # RaspberryPi
    os.environ["BLINKA_FORCEBOARD"] = "RASPBERRY_PI_3A_PLUS"  # Raspberry Pi 3 Model A Plus Rev 1.0
    os.environ["FIRMWARE"] = "1.0"
    os.environ["HARDWARE"] = "1.2"
