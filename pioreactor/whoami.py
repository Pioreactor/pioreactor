# -*- coding: utf-8 -*-
import sys
import os
from functools import lru_cache

UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


def get_latest_testing_experiment_name() -> str:
    exp = get_latest_experiment_name()
    return f"_testing_{exp}"


@lru_cache(maxsize=1)
def get_latest_experiment_name() -> str:

    if os.environ.get("EXPERIMENT") is not None:
        return os.environ["EXPERIMENT"]
    elif is_testing_env():
        return "_testing_experiment"

    from pioreactor.pubsub import subscribe

    mqtt_msg = subscribe("pioreactor/latest_experiment", timeout=1)
    if mqtt_msg:
        return mqtt_msg.payload.decode()
    else:
        from pioreactor.logging import create_logger

        logger = create_logger("pioreactor")
        logger.info(
            "No experiment running, exiting. Try creating a new experiment first."
        )
        logger.info(
            "No experiment found in `pioreactor/latest_experiment` topic in MQTT, exiting."
        )
        sys.exit()


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
    from pioreactor.config import leader_hostname

    return get_unit_name() == leader_hostname


def am_I_active_worker() -> bool:
    from pioreactor.config import get_active_workers_in_inventory

    return get_unit_name() in get_active_workers_in_inventory()


def get_uuid() -> str:
    from uuid import getnode

    return str(getnode())


def get_rpi_machine() -> str:
    if not is_testing_env():
        from board import detector  # type: ignore

        return detector.get_device_model()
    else:
        return "Raspberry Pi 4 - testing"


if is_testing_env():
    import fake_rpi  # type: ignore

    sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
    sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO
