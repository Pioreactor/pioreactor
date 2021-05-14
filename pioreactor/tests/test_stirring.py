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
    stirring(500, duration=0.1)


def test_change_stirring_mid_cycle():
    original_rpm = 500

    st = Stirrer(original_rpm, unit, exp)
    assert st.rpm == original_rpm
    pause()

    new_rpm = 750
    publish(f"pioreactor/{unit}/{exp}/stirring/rpm/set", new_rpm)

    pause()

    assert st.rpm == new_rpm
    assert st.state == "ready"

    publish(f"pioreactor/{unit}/{exp}/stirring/rpm/set", 0)
    pause()
    assert st.rpm == 0
    pause()


def test_pause_stirring_mid_cycle():
    original_rpm = 500

    st = Stirrer(original_rpm, unit, exp)
    assert st.rpm == original_rpm
    pause()

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "sleeping")
    pause()

    assert st.rpm == 0

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "ready")
    pause()

    assert st.rpm == 500


def test_pause_stirring_mid_cycle_with_modified_rpm():
    original_rpm = 500

    st = Stirrer(original_rpm, unit, exp)
    assert st.rpm == original_rpm

    new_rpm = 800
    publish(f"pioreactor/{unit}/{exp}/stirring/rpm/set", new_rpm)

    pause()

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "sleeping")
    pause()

    assert st.rpm == 0

    publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "ready")
    pause()

    assert st.rpm == new_rpm


def test_publish_duty_cycle():
    publish(f"pioreactor/{unit}/{exp}/stirring/rpm", None, retain=True)
    pause()
    original_rpm = 500

    st = Stirrer(original_rpm, unit, exp)
    assert st.rpm == original_rpm

    pause()
    message = subscribe(f"pioreactor/{unit}/{exp}/stirring/rpm")
    assert float(message.payload) == 500


"""
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
    adc_reader.start_periodic_reading()
    pause()
    pause()

    time.sleep(19)
    assert st.duty_cycle == original_dc
    time.sleep(2)
    assert st.duty_cycle == 70
    time.sleep(2)
    assert st.duty_cycle == original_dc
    time.sleep(7)

    publish(f"pioreactor/{unit}/{exp}/stirring/dc_increase_between_adc_readings/set", 0)

    adc_reader.set_state("disconnected")
    assert True
"""
