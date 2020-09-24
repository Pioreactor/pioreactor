# -*- coding: utf-8 -*-
import sys
import configparser
import socket
from functools import wraps

import numpy as np


def get_leader_hostname():
    if "pytest" in sys.modules:
        return "localhost"
    else:
        return get_config()["network"]["leader_hostname"]


def get_hostname():
    if "pytest" in sys.modules:
        return "localhost"
    else:
        return socket.gethostname()


def get_config():
    config = configparser.ConfigParser()
    config.read("config.ini")
    return config


def get_unit_from_hostname():
    import re

    hostname = get_hostname()

    if hostname == "leader":
        # running from the leader Rpi
        return "0"
    elif hostname == "localhost":
        # running tests
        return "_testing"
    elif re.match(r"morbidostat(\d)", hostname):
        # running from a worker Rpi
        # TODO: turn me into walrus operator
        return re.match(r"morbidostat(\d)", hostname).groups()[0]
    elif hostname == "raspberrypi":
        raise ValueError("Did you forget to set the hostname?")
    else:
        return "unknown"


def pump_ml_to_duration(ml, dc, dc_=0, duration_=0, intercept_=0):
    """
    log(ml) = dc_ * log(duty_cycle) + duration_ * log(duration) + intercept_
    """
    duration = np.exp(1 / duration_ * (np.log(ml) - dc_ * np.log(dc) - intercept_))
    return duration


def execute_sql_statement(SQL):
    import pandas as pd
    import sqlite3

    db_location = config["data"]["observation_database"]
    conn = sqlite3.connect(db_location)
    df = pd.read_sql_query(SQL, conn)
    conn.close()
    return df


def get_latest_experiment_name():
    if "pytest" in sys.modules:
        return "_experiment"

    from morbidostat.utils.pubsub import subscribe

    return str(subscribe("morbidostat/latest_experiment").payload)


leader_hostname = get_leader_hostname()
config = get_config()
unit = get_unit_from_hostname()
