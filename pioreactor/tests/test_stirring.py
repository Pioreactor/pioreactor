# -*- coding: utf-8 -*-
# test_stirring
import time
import pytest
from pioreactor.background_jobs.stirring import stirring, Stirrer
from pioreactor.whoami import unit, experiment as exp
from pioreactor.pubsub import publish, subscribe


def pause():
    # to avoid race conditions
    time.sleep(0.5)


def test_stirring_runs():
    stirring(50, verbose=2, duration=0.1)


def test_change_stirring_mid_cycle():
    original_dc = 50

    st = Stirrer(original_dc, unit, exp, verbose=2)
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
    assert st.state == "sleeping"
    pause()


def test_pause_stirring_mid_cycle():
    original_dc = 50

    st = Stirrer(original_dc, unit, exp, verbose=2)
    assert st.duty_cycle == original_dc
    pause()

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "sleeping")
    pause()

    assert st.duty_cycle == 0

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "ready")
    pause()

    assert st.duty_cycle == 50


def test_publish_duty_cycle():
    publish(f"pioreactor/{unit}/{exp}/stirring/duty_cycle", None, retain=True)
    pause()
    original_dc = 50

    st = Stirrer(original_dc, unit, exp, verbose=2)
    assert st.duty_cycle == original_dc

    pause()
    message = subscribe(f"pioreactor/{unit}/{exp}/stirring/duty_cycle")
    assert float(message.payload) == 50
