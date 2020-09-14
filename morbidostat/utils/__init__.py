import configparser
import sqlite3


config = configparser.ConfigParser()
config.read("config.ini")
leader_hostname = config["network"]["leader_hostname"]


def pump_ml_to_duration(ml, rate, bias):
    """
    ml = rate * duration + bias
    """
    duration = (ml - bias) / rate
    assert duration >= 0, "pump duration is negative"
    return duration


def execute_sql_statement(SQL):
    import pandas as pd
    db_location = config["data"]["observation_database"]
    conn = sqlite3.connect(db_location)
    df = pd.read_sql_query(SQL, conn)
    conn.close()
    return df
