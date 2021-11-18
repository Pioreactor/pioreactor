# -*- coding: utf-8 -*-
# test_monitor
import time
from pioreactor.background_jobs.monitor import Monitor
from pioreactor.whoami import (
    get_latest_experiment_name,
    get_unit_name,
    UNIVERSAL_EXPERIMENT,
)
from pioreactor.pubsub import publish, subscribe


def test_check_job_states_in_monitor() -> None:
    unit = get_unit_name()
    exp = UNIVERSAL_EXPERIMENT

    # suppose od_reading is READY when monitor starts, but isn't actually running, ex after a reboot on a worker.
    publish(
        f"pioreactor/{unit}/{get_latest_experiment_name()}/od_reading/$state",
        "ready",
        retain=True,
    )

    with Monitor(unit=unit, experiment=exp):

        time.sleep(10)
        value = subscribe(
            f"pioreactor/{unit}/{get_latest_experiment_name()}/od_reading/$state"
        )
        assert value.payload.decode() == "lost"
