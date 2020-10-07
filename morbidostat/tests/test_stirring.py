# -*- coding: utf-8 -*-
# test_stirring
import time
import pytest
from morbidostat.background_jobs.stirring import stirring, Stirrer
from morbidostat.utils import get_latest_experiment_name, get_unit_from_hostname
from morbidostat.utils.pubsub import publish


def test_stirring():
    stirring(50, verbose=True, duration=0.1)


def test_change_stirring_mid_cycle():
    original_dc = 50
    unit = get_unit_from_hostname()
    exp = get_latest_experiment_name()

    st = Stirrer(original_dc, unit, exp, verbose=True)
    assert st.duty_cycle == original_dc
    time.sleep(0.5)

    new_dc = 75
    publish(f"morbidostat/{unit}/{exp}/stirring/duty_cycle", new_dc)

    time.sleep(0.5)

    assert st.duty_cycle == new_dc
