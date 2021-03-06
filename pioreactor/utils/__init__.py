# -*- coding: utf-8 -*-
from dbm import ndbm
from contextlib import contextmanager
from pioreactor.whoami import am_I_leader


@contextmanager
def local_intermittent_storage(cache_name):
    try:
        cache = ndbm.open(f"/tmp/{cache_name}", "c")
        yield cache
    finally:
        cache.close()


def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))


def correlation(x, y):
    from statistics import stdev, mean

    mean_x, std_x = mean(x), stdev(x)
    mean_y, std_y = mean(y), stdev(y)

    if (std_y == 0) or (std_x == 0):
        return 0

    running_sum = 0
    running_count = 0
    for (x_, y_) in zip(x, y):
        running_sum += (x_ - mean_x) * (y_ - mean_y)
        running_count += 1

    if running_count < 1:
        return 0

    return (running_sum / (running_count - 1)) / std_y / std_x


def is_pio_job_running(target_job):
    with local_intermittent_storage("pio_jobs_running") as cache:
        return cache.get(target_job, b"0") == b"1"


def pio_jobs_running():
    """
    This returns a list of the current pioreactor jobs/actions running. Ex:

    > ["stirring", "air_bubbler", "stirring"]

    Notes
    -------
    Duplicate jobs can show up here, as in the case when a job starts while another
    job runs (hence why this needs to be a list and not a set.)

    This function is slow, takes about 0.1s on a RaspberryPi, so it's preferred to use
    `is_pio_job_runnning` first, and use this as a backup to double check.

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
