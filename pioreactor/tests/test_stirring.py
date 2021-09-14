# -*- coding: utf-8 -*-

import time
from pioreactor.background_jobs.stirring import start_stirring, Stirrer
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.pubsub import publish, subscribe

unit = get_unit_name()
exp = get_latest_experiment_name()


def pause():
    # to avoid race conditions
    time.sleep(0.5)


def test_stirring_runs():
    st = start_stirring(50)
    st.set_state(st.DISCONNECTED)


def test_change_stirring_mid_cycle():
    original_dc = 50

    st = Stirrer(original_dc, unit, exp)
    assert st.duty_cycle == original_dc
    pause()

    new_dc = 75
    publish(f"pioreactor/{unit}/{exp}/stirring/duty_cycle/set", new_dc)

    pause()

    assert st.duty_cycle == new_dc
    assert st.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/stirring/duty_cycle/set", 0)
    pause()
    assert st.duty_cycle == 0
    pause()
    st.set_state(st.DISCONNECTED)


def test_pause_stirring_mid_cycle():
    original_dc = 50

    st = Stirrer(original_dc, unit, exp)
    assert st.duty_cycle == original_dc
    pause()

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "sleeping")
    pause()

    assert st.duty_cycle == 0

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "ready")
    pause()

    assert st.duty_cycle == 50
    st.set_state(st.DISCONNECTED)


def test_pause_stirring_mid_cycle_with_modified_dc():
    original_dc = 50

    st = Stirrer(original_dc, unit, exp)
    assert st.duty_cycle == original_dc

    new_dc = 80
    publish(f"pioreactor/{unit}/{exp}/stirring/duty_cycle/set", new_dc)

    pause()

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "sleeping")
    pause()

    assert st.duty_cycle == 0

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "ready")
    pause()

    assert st.duty_cycle == new_dc
    st.set_state(st.DISCONNECTED)


def test_publish_duty_cycle():
    publish(f"pioreactor/{unit}/{exp}/stirring/duty_cycle", None, retain=True)
    pause()
    original_dc = 50

    st = Stirrer(original_dc, unit, exp)
    assert st.duty_cycle == original_dc

    pause()
    message = subscribe(f"pioreactor/{unit}/{exp}/stirring/duty_cycle")
    assert float(message.payload) == 50
    st.set_state(st.DISCONNECTED)
