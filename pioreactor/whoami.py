# -*- coding: utf-8 -*-
import sys
import os

UNIVERSAL_IDENTIFIER = "$broadcast"
UNIVERSAL_EXPERIMENT = "$experiment"
NO_EXPERIMENT = "$no_experiment_present"


def get_latest_experiment_name():
    if "pytest" in sys.modules or os.environ.get("TESTING"):
        return "testing_experiment"

    from pioreactor.utils import execute_query_against_db

    rows = execute_query_against_db(
        "SELECT experiment FROM experiments ORDER BY timestamp DESC LIMIT 1;"
    )
    if rows:
        return rows[0]
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
