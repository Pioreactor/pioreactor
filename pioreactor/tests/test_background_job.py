# -*- coding: utf-8 -*-
import time

from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.pubsub import publish


def pause():
    # to avoid race conditions
    time.sleep(0.5)


def test_states():
    unit = get_unit_name()
    exp = get_latest_experiment_name()

    bj = BackgroundJob(job_name="job", unit=unit, experiment=exp)
    pause()
    assert bj.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "sleeping")
    pause()
    assert bj.state == "sleeping"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "ready")
    pause()
    assert bj.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "init")
    pause()
    assert bj.state == "init"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "disconnected")
    pause()
