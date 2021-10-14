# -*- coding: utf-8 -*-

import time, json
from pioreactor.background_jobs.stirring import (
    start_stirring,
    Stirrer,
    RpmCalculator,
    RpmFromFrequency,
)
from pioreactor.utils import local_persistant_storage
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.pubsub import publish, subscribe

unit = get_unit_name()
exp = get_latest_experiment_name()


def pause():
    # to avoid race conditions
    time.sleep(0.5)


def test_stirring_runs():
    st = start_stirring(target_rpm=500)
    st.set_state(st.DISCONNECTED)


def test_change_target_rpm_mid_cycle():
    original_rpm = 500

    st = Stirrer(original_rpm, unit, exp, rpm_calculator=RpmCalculator())
    assert st.target_rpm == original_rpm
    pause()

    new_rpm = 750
    publish(f"pioreactor/{unit}/{exp}/stirring/target_rpm/set", new_rpm)

    pause()

    assert st.target_rpm == new_rpm
    assert st.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/stirring/target_rpm/set", 0)
    pause()
    assert st.target_rpm == 0
    pause()
    st.set_state(st.DISCONNECTED)


def test_pause_stirring_mid_cycle():

    st = Stirrer(500, unit, exp, rpm_calculator=RpmCalculator())
    original_dc = st.duty_cycle
    pause()

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "sleeping")
    pause()

    assert st.duty_cycle == 0

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "ready")
    pause()

    assert st.duty_cycle == original_dc
    st.set_state(st.DISCONNECTED)


def test_publish_target_rpm():
    publish(f"pioreactor/{unit}/{exp}/stirring/target_rpm", None, retain=True)
    pause()
    target_rpm = 500

    st = Stirrer(target_rpm, unit, exp, rpm_calculator=RpmCalculator())
    assert st.target_rpm == target_rpm

    pause()
    message = subscribe(f"pioreactor/{unit}/{exp}/stirring/target_rpm")
    assert float(message.payload) == 500
    st.set_state(st.DISCONNECTED)


def test_publish_measured_rpm():
    publish(f"pioreactor/{unit}/{exp}/stirring/measured_rpm", None, retain=True)
    pause()
    target_rpm = 500

    st = Stirrer(target_rpm, unit, exp, rpm_calculator=RpmFromFrequency())
    st.start_stirring()
    assert st.target_rpm == target_rpm

    pause()

    message = subscribe(f"pioreactor/{unit}/{exp}/stirring/measured_rpm")
    assert json.loads(message.payload)["rpm"] == 0
    st.set_state(st.DISCONNECTED)


def test_stirring_with_lookup_linear_v1():

    with local_persistant_storage("stirring_calibration") as cache:
        cache["linear_v1"] = json.dumps({"rpm_coef": 0.1, "intercept": 20})

    target_rpm = 500
    st = Stirrer(target_rpm, unit, exp, rpm_calculator=None)
    st.start_stirring()

    assert st.duty_cycle == 60 - 0.9 * (60 - (0.1 * target_rpm + 20))

    dc = st.duty_cycle
    target_rpm = 600
    publish(f"pioreactor/{unit}/{exp}/stirring/target_rpm/set", 600)
    pause()
    pause()

    assert st.duty_cycle == dc - 0.9 * (dc - (0.1 * target_rpm + 20))

    st.set_state(st.DISCONNECTED)
