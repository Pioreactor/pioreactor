# -*- coding: utf-8 -*-


def pio_jobs_running():
    import psutil

    jobs = set([])
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            if (
                proc.info["cmdline"]
                and (proc.info["cmdline"][0] == "/usr/bin/python3")
                and (proc.info["cmdline"][1] == "/usr/local/bin/pio")  # not pios!
            ):
                # TODO: needs to be more specific, this fails often
                job = proc.info["cmdline"][3]
                jobs.add(job)
        except Exception:
            pass
    return jobs


def execute_query_against_db(query):
    # must run on leader
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
