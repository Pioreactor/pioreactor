# -*- coding: utf-8 -*-
from pioreactor.whoami import am_I_leader


def pio_jobs_running():
    """
    This returns a list of the current pioreactor jobs/actions running. Ex:

    > ["stirring", "air_bubbler", "stirring"]

    Notes
    -------
    Duplicate jobs can show up here, as in the case when a job starts while another
    job runs (hence why this needs to be a list and not a set.)

    """
    import psutil

    jobs = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            if (
                proc.info["cmdline"]
                and (proc.info["cmdline"][0] == "/usr/bin/python3")
                and (proc.info["cmdline"][1] == "/usr/local/bin/pio")  # not pios!
            ):
                job = proc.info["cmdline"][3]
                jobs.append(job)
        except Exception:
            pass
    return jobs


def execute_query_against_db(query):
    if not am_I_leader():
        raise IOError("Need to be leader to run this.")

    import sqlite3
    from pioreactor.config import config

    conn = sqlite3.connect(config["storage"]["database"])
    cur = conn.cursor()
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    return rows


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
