# -*- coding: utf-8 -*-
import sys
import os

UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


def get_latest_experiment_name():
    if "pytest" in sys.modules or os.environ.get("TESTING"):
        return "testing_experiment"

    from pioreactor.pubsub import subscribe

    mqtt_msg = subscribe("pioreactor/latest_experiment", timeout=1)
    if mqtt_msg:
        return mqtt_msg.payload.decode()
    else:
        return NO_EXPERIMENT


def get_hostname():
    import socket

    if "pytest" in sys.modules:
        return "localhost"
    elif os.environ.get("HOSTNAME"):
        return os.environ.get("HOSTNAME")
    else:
        return socket.gethostname()


def get_unit_name():

    hostname = get_hostname()

    if hostname == "leader":
        # running from the leader Rpi
        return "leader"
    elif hostname == "localhost":
        # running tests
        return "testing_unit"
    elif hostname == "raspberrypi":
        raise ValueError("Did you forget to set the hostname?")
    else:
        return hostname


def am_I_leader():
    from pioreactor.config import leader_hostname

    return get_unit_name() == leader_hostname


def am_I_active_worker():
    from pioreactor.config import get_active_worker_units_and_ips

    return get_unit_name() in get_active_worker_units_and_ips().keys()
