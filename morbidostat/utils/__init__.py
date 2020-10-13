# -*- coding: utf-8 -*-
import sys
import configparser
import socket
import os
import signal
from functools import wraps

import numpy as np


def log_start(unit, experiment):
    def actual_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from morbidostat.pubsub import publish

            func_name = func.__name__
            publish(f"morbidostat/{unit}/{experiment}/log", f"[{func_name}]: starting.", verbose=1)
            return func(*args, **kwargs)

        return wrapper

    return actual_decorator


def log_stop(unit, experiment):
    def actual_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            from morbidostat.pubsub import publish

            func_name = func.__name__

            def terminate(*args):
                publish(f"morbidostat/{unit}/{experiment}/log", f"[{func_name}]: terminated.", verbose=verbose)
                sys.exit()

            signal.signal(signal.SIGTERM, terminate)

            return func(*args, **kwargs)

        return wrapper

    return actual_decorator


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
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../config.ini")
    config.read(config_path)
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


def pump_ml_to_duration(ml, duty_cycle, duration_=0):
    """
    ml: the desired volume
    duration_ : the coefficient from calibration
    """
    return ml / duration_


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

    from morbidostat.pubsub import subscribe

    return str(subscribe("morbidostat/latest_experiment").payload, "utf-8")


leader_hostname = get_leader_hostname()
config = get_config()
unit = get_unit_from_hostname()
experiment = get_latest_experiment_name()
