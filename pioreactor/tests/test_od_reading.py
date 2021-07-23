# -*- coding: utf-8 -*-
# test_od_reading.py

import time, json
from pioreactor.background_jobs.od_reading import TemperatureCompensator
from pioreactor.whoami import get_latest_experiment_name, get_unit_name
from pioreactor.pubsub import publish


def pause():
    time.sleep(0.25)


def test_TemperatureCompensator():

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    # mock
    TemperatureCompensator.get_initial_temperature = lambda self: 25.0

    tc = TemperatureCompensator(unit=unit, experiment=experiment)

    assert tc.compensate_od_for_temperature(1.0) == 1.0

    publish(
        f"pioreactor/{unit}/{experiment}/temperature_control/temperature",
        json.dumps({"temperature": 30, "timestamp": "2020-10-01"}),
    )

    pause()

    # suppose temp increased, but OD stayed the same
    assert tc.compensate_od_for_temperature(1.0) > 1.0
