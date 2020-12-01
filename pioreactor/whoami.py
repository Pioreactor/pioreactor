# -*- coding: utf-8 -*-
import sys
import os
import socket

UNIVERSAL_IDENTIFIER = "$broadcast"


def get_latest_experiment_name():
    if "pytest" in sys.modules or os.environ.get("TESTING"):
        return "_testing_experiment"

    from pioreactor.pubsub import subscribe

    mqtt_msg = subscribe("pioreactor/latest_experiment", timeout=1)
    if mqtt_msg:
        return mqtt_msg.payload.decode()
    else:
        return None


def get_hostname():
    if "pytest" in sys.modules:
        return "localhost"
    elif os.environ.get("HOSTNAME"):
        return os.environ.get("HOSTNAME")
    else:
        return socket.gethostname()


def get_unit_from_hostname():
    import re

    hostname = get_hostname()

    if hostname == "leader":
        # running from the leader Rpi
        return "leader"
    elif hostname == "localhost":
        # running tests
        return "_testing_unit"
    elif re.match(r"pioreactor(\d)", hostname):
        # running from a worker Rpi
        # TODO: turn me into walrus operator
        return re.match(r"pioreactor(\d)", hostname).groups()[0]
    elif hostname == "raspberrypi":
        raise ValueError("Did you forget to set the hostname?")
    else:
        raise ValueError(f"How did I get here? My hostname is {hostname}")


def am_I_leader():
    from pioreactor.config import leader_hostname

    return get_hostname() == leader_hostname
