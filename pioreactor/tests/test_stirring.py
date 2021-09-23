# -*- coding: utf-8 -*-

import time
from pioreactor.background_jobs.stirring import (
    start_stirring,
    Stirrer,
    RpmCalculator,
    RpmFromFrequency,
)
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


def test_publish_actual_rpm():
    publish(f"pioreactor/{unit}/{exp}/stirring/actual_rpm", None, retain=True)
    pause()
    target_rpm = 500

    st = Stirrer(target_rpm, unit, exp, rpm_calculator=RpmFromFrequency())
    st.start_stirring()
    assert st.target_rpm == target_rpm

    pause()

    message = subscribe(f"pioreactor/{unit}/{exp}/stirring/actual_rpm")
    assert float(message.payload) == 0
    st.set_state(st.DISCONNECTED)
