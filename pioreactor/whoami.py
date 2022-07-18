# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from functools import lru_cache

UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


def get_latest_testing_experiment_name() -> str:
    exp = get_latest_experiment_name()
    return f"_testing_{exp}"


@lru_cache(maxsize=1)
def get_latest_experiment_name() -> str:
    return _get_latest_experiment_name()


def _get_latest_experiment_name() -> str:

    if os.environ.get("EXPERIMENT") is not None:
        return os.environ["EXPERIMENT"]
    elif is_testing_env():
        return "_testing_experiment"

    from pioreactor.pubsub import subscribe

    mqtt_msg = subscribe(
        "pioreactor/latest_experiment",
        timeout=30,
        retries=2,
        name="get_latest_experiment_name",
    )
    if mqtt_msg:
        return mqtt_msg.payload.decode()
    else:
        from pioreactor.logging import create_logger

        logger = create_logger("pioreactor", experiment=UNIVERSAL_EXPERIMENT, to_mqtt=False)
        logger.warning("No experiment found. Try creating a new experiment first.")
        return NO_EXPERIMENT


@lru_cache(maxsize=1)
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


def get_unit_name() -> str:

    hostname = get_hostname()

    if hostname == "raspberrypi":
        raise ValueError("Did you forget to set the hostname?")
    else:
        return hostname


def am_I_leader() -> bool:
    if is_testing_env():
        return True

    from pioreactor.config import leader_hostname

    return get_unit_name() == leader_hostname


def am_I_active_worker() -> bool:
    if is_testing_env():
        return True

    from pioreactor.config import get_active_workers_in_inventory

    return get_unit_name() in get_active_workers_in_inventory()


@lru_cache(maxsize=1)
def get_uuid() -> str:
    from uuid import getnode
    from hashlib import md5

    id_ = str(getnode())  # MAC address of a network interface
    return md5(id_.encode()).hexdigest()


def get_rpi_machine() -> str:
    if not is_testing_env():
        with open("/proc/device-tree/model") as f:
            return f.read()
    else:
        return "Raspberry Pi 3 - testing"


if is_testing_env():
    import fake_rpi  # type: ignore

    fake_rpi.toggle_print(False)
    sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
    sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO

    # allow Blinka to think we are an Rpi:
    # https://github.com/adafruit/Adafruit_Python_PlatformDetect/blob/75f69806222fbaf8535130ed2eacd07b06b1a298/adafruit_platformdetect/board.py
    os.environ["BLINKA_FORCECHIP"] = "BCM2XXX"  # RaspberryPi
    os.environ["BLINKA_FORCEBOARD"] = "RASPBERRY_PI_3A_PLUS"  # Raspberry Pi 3 Model A Plus Rev 1.0
