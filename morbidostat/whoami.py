# -*- coding: utf-8 -*-
import re
import sys
import os
import socket
from morbidostat.config import leader_hostname


def get_latest_experiment_name():
    if "pytest" in sys.modules or os.environ.get("TESTING"):
        return "_testing_experiment"

    from morbidostat.pubsub import subscribe

    return str(subscribe("morbidostat/latest_experiment").payload, "utf-8")


def get_hostname():
    if "pytest" in sys.modules:
        return "localhost"
    else:
        return socket.gethostname()


def get_unit_from_hostname():

    hostname = get_hostname()

    if hostname == "leader":
        # running from the leader Rpi
        return "leader"
    elif hostname == "localhost":
        # running tests
        return "_testing_unit"
    elif re.match(r"morbidostat(\d)", hostname):
        # running from a worker Rpi
        # TODO: turn me into walrus operator
        return re.match(r"morbidostat(\d)", hostname).groups()[0]
    elif hostname == "raspberrypi":
        raise ValueError("Did you forget to set the hostname?")
    else:
        return "unknown"


def am_I_leader():
    return get_hostname() == leader_hostname


unit = get_unit_from_hostname()
experiment = get_latest_experiment_name()
