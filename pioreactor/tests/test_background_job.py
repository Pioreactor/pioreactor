# -*- coding: utf-8 -*-
# test background_job
import pytest
import time

from pioreactor.background_jobs import BackgroundJob
from pioreactor.whoami import unit, experiment as exp
from pioreactor.pubsub import publish


def pause():
    # to avoid race conditions
    time.sleep(0.5)


def test_states():

    bj = BackgroundJob(job_name="job", unit=unit, experiment=exp)
    pause()
    assert bj.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "sleeping")
    pause()
    assert bj.state == "sleeping"

    publish(f"pioreactor/{unit}/{exp}/job/$state/set", "disconnected")
    pause()
