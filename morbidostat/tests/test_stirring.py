# -*- coding: utf-8 -*-
# test_stirring
import time
import pytest
from morbidostat.background_jobs.stirring import stirring, Stirrer
from morbidostat.utils import unit, experiment as exp
from morbidostat.pubsub import publish


def pause():
    # to avoid race conditions
    time.sleep(0.5)


def test_stirring():
    stirring(50, verbose=2, duration=0.1)


def test_change_stirring_mid_cycle():
    original_dc = 50

    st = Stirrer(original_dc, unit, exp, verbose=2)
    assert st.duty_cycle == original_dc
    pause()

    new_dc = 75
    publish(f"morbidostat/{unit}/{exp}/stirring/duty_cycle", new_dc)

    pause()

    assert st.duty_cycle == new_dc
