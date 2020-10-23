# -*- coding: utf-8 -*-
import sys
import socket
import os
import signal
import json
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
                publish(f"morbidostat/{unit}/{experiment}/log", f"[{func_name}]: terminated.", verbose=2)
                sys.exit()

            signal.signal(signal.SIGTERM, terminate)

            return func(*args, **kwargs)

        return wrapper

    return actual_decorator


def pump_ml_to_duration(ml, duty_cycle, duration_=0):
    """
    ml: the desired volume
    duration_ : the coefficient from calibration
    """
    return ml / duration_


def pump_duration_to_ml(duration, duty_cycle, duration_=0):
    """
    duration: the desired volume
    duration_ : the coefficient from calibration
    """
    return duration * duration_


def execute_sql_statement(SQL):
    import pandas as pd
    import sqlite3

    db_location = config["data"]["observation_database"]
    conn = sqlite3.connect(db_location)
    df = pd.read_sql_query(SQL, conn)
    conn.close()
    return df
