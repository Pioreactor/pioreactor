import sys
import configparser
import socket

def get_leader_hostname():
    if "pytest" in sys.modules:
        return "localhost"
    else:
        return get_config()["network"]["leader_hostname"]

def get_hostname():
    if "pytest" in sys.modules:
        return "localhost0"
    else:
        return socket.gethostname()

def get_config():
    config = configparser.ConfigParser()
    config.read("config.ini")
    return config

def assert_unit_matches_hostname(unit):
    hostname = get_hostname()
    assert str(unit) == str(hostname[-1]), "Hostname does not match unit"


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