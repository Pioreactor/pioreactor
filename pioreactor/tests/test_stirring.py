# -*- coding: utf-8 -*-

import time
from pioreactor.background_jobs.stirring import stirring, Stirrer
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.pubsub import publish, subscribe

unit = get_unit_name()
exp = get_latest_experiment_name()


def pause():
    # to avoid race conditions
    time.sleep(0.5)


def test_stirring_runs():
    stirring(50, duration=0.1)


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


def test_publish_duty_cycle():
    publish(f"pioreactor/{unit}/{exp}/stirring/duty_cycle", None, retain=True)
    pause()
    original_dc = 50

    st = Stirrer(original_dc, unit, exp)
    assert st.duty_cycle == original_dc

    pause()
    message = subscribe(f"pioreactor/{unit}/{exp}/stirring/duty_cycle")
    assert float(message.payload) == 50


def test_dynamic_stirring():

    from pioreactor.background_jobs.od_reading import ADCReader

    # clear cache
    publish(f"pioreactor/{unit}/{exp}/adc_reader/first_ads_obs_time", None, retain=True)
    publish(f"pioreactor/{unit}/{exp}/adc_reader/interval", None, retain=True)
    pause()

    original_dc = 50
    st = Stirrer(original_dc, unit, exp, dc_increase_between_adc_readings=True)
    pause()

    adc_reader = ADCReader(interval=5, unit=unit, experiment=exp, fake_data=True)
    adc_reader.setup_adc()
    pause()

    time.sleep(15)
    assert st.duty_cycle == original_dc
    time.sleep(2)
    assert st.duty_cycle == 75
    time.sleep(2)
    assert st.duty_cycle == original_dc
    time.sleep(7)

    publish(f"pioreactor/{unit}/{exp}/stirring/dc_increase_between_adc_readings/set", 0)

    adc_reader.set_state("disconnected")
    assert True
