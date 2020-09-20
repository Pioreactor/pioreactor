# -*- coding: utf-8 -*-
import sys
import configparser
import socket
from functools import wraps
import paho.mqtt.subscribe as paho_subscribe


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
        raise ValueError("Unsure where this is being run from...")


def pump_ml_to_duration(ml, rate, bias):
    """
    ml = rate * duration + bias
    """
    duration = (ml - bias) / rate
    assert duration >= 0, "pump duration is negative"
    return duration


def execute_sql_statement(SQL):
    import pandas as pd
    import sqlite3

    db_location = config["data"]["observation_database"]
    conn = sqlite3.connect(db_location)
    df = pd.read_sql_query(SQL, conn)
    conn.close()
    return df


leader_hostname = get_leader_hostname()
config = get_config()
unit = get_unit_from_hostname()


def exit(*args, **kwargs):
    import sys

    sys.exit()
