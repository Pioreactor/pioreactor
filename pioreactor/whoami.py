# -*- coding: utf-8 -*-
import sys
import os
from functools import lru_cache

UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


@lru_cache(maxsize=1)
def get_latest_experiment_name():

    if os.environ.get("EXPERIMENT"):
        return os.environ.get("EXPERIMENT")
    elif is_testing_env():
        return "testing_experiment"

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


def is_testing_env():
    return "pytest" in sys.modules or os.environ.get("TESTING")


def get_hostname():
    import socket

    if os.environ.get("HOSTNAME"):
        return os.environ.get("HOSTNAME")
    elif is_testing_env():
        return "testing_unit"
    else:
        return socket.gethostname()


def get_unit_name():

    hostname = get_hostname()

    if hostname == "raspberrypi":
        raise ValueError("Did you forget to set the hostname?")
    else:
        return hostname


def am_I_leader():
    from pioreactor.config import leader_hostname

    return get_unit_name() == leader_hostname


def am_I_active_worker():
    from pioreactor.config import get_active_workers_in_inventory

    return get_unit_name() in get_active_workers_in_inventory()
