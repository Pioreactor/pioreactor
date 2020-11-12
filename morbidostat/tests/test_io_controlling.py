# -*- coding: utf-8 -*-
import time
import json
import pytest

from morbidostat.background_jobs.io_controlling import io_controlling, ControlAlgorithm, PIDMorbidostat, PIDTurbidostat
from morbidostat.background_jobs.utils import events
from morbidostat.whoami import unit, experiment
from morbidostat import pubsub


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.5)


def test_silent_algorithm():
    io = io_controlling(mode="silent", volume=None, duration=60, verbose=2)
    pause()
    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", "0.01")
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", "1.0")
    pause()
    assert isinstance(next(io), events.NoEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", "0.02")
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", "1.1")
    pause()
    assert isinstance(next(io), events.NoEvent)


def test_turbidostat_algorithm():
    target_od = 1.0
    algo = io_controlling(mode="turbidostat", target_od=target_od, duration=60, volume=0.25, verbose=2)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.98)
    pause()
    assert isinstance(next(algo), events.NoEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 1.0)
    pause()
    assert isinstance(next(algo), events.DilutionEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 1.01)
    pause()
    assert isinstance(next(algo), events.DilutionEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.99)
    pause()
    assert isinstance(next(algo), events.NoEvent)


def test_pid_turbidostat_algorithm():

    target_od = 2.4
    algo = io_controlling(mode="pid_turbidostat", target_od=target_od, volume=2.0, duration=30, verbose=2)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 3.2)
    pause()
    e = next(algo)
    assert isinstance(e, events.DilutionEvent)
    assert e.volume_to_cycle > 1.0

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 3.1)
    pause()
    e = next(algo)
    assert isinstance(e, events.DilutionEvent)
    assert e.volume_to_cycle > 1.0


def test_morbidostat_algorithm():
    target_od = 1.0
    algo = io_controlling(mode=f"morbidostat", target_od=target_od, duration=60, volume=0.25, verbose=2)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.95)
    pause()
    assert isinstance(next(algo), events.NoEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.99)
    pause()
    assert isinstance(next(algo), events.DilutionEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 1.05)
    pause()
    assert isinstance(next(algo), events.AltMediaEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 1.03)
    pause()
    assert isinstance(next(algo), events.DilutionEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 1.04)
    pause()
    assert isinstance(next(algo), events.AltMediaEvent)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.01)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.99)
    pause()
    assert isinstance(next(algo), events.DilutionEvent)


def test_pid_morbidostat_algorithm():
    target_growth_rate = 0.09
    algo = io_controlling(mode="pid_morbidostat", target_od=1.0, target_growth_rate=target_growth_rate, duration=60, verbose=2)

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.08)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.500)
    pause()
    assert isinstance(next(algo), events.NoEvent)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.08)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.95)
    pause()
    assert isinstance(next(algo), events.AltMediaEvent)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.07)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.95)
    pause()
    assert isinstance(next(algo), events.AltMediaEvent)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.065)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.95)
    pause()
    assert isinstance(next(algo), events.AltMediaEvent)


def test_changing_morbidostat_parameters_over_mqtt():

    target_growth_rate = 0.05
    algo = PIDMorbidostat(
        target_growth_rate=target_growth_rate, target_od=1.0, duration=60, verbose=2, unit=unit, experiment=experiment
    )
    assert algo.target_growth_rate == target_growth_rate
    pause()
    new_target = 0.07
    pubsub.publish(f"morbidostat/{unit}/{experiment}/io_controlling/target_growth_rate/set", new_target)
    pause()
    assert algo.target_growth_rate == new_target
    assert algo.pid.pid.setpoint == new_target


def test_changing_turbidostat_params_over_mqtt():

    og_volume = 0.5
    og_target_od = 1.0
    algo = PIDTurbidostat(volume=og_volume, target_od=og_target_od, duration=0.0001, verbose=2, unit=unit, experiment=experiment)
    assert algo.volume == og_volume

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.05)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 1.0)
    pause()
    algo.run()

    pubsub.publish(f"morbidostat/{unit}/{experiment}/io_controlling/volume/set", 1.0)
    pause()

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.05)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 1.0)
    algo.run()

    assert algo.volume == 1.0

    new_od = 1.5
    pubsub.publish(f"morbidostat/{unit}/{experiment}/io_controlling/target_od/set", new_od)
    pause()
    assert algo.target_od == new_od
    assert algo.pid.pid.setpoint == new_od
    assert algo.min_od == 0.75 * new_od


def test_changing_parameters_over_mqtt_with_unknown_parameter():

    algo = ControlAlgorithm(target_growth_rate=0.05, target_od=1.0, duration=60, verbose=2, unit=unit, experiment=experiment)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/io_controlling/garbage/set", 0.07)
    pause()


def test_pause_in_io_controlling():

    algo = ControlAlgorithm(target_growth_rate=0.05, target_od=1.0, duration=60, verbose=2, unit=unit, experiment=experiment)
    pause()
    pubsub.publish(f"morbidostat/{unit}/{experiment}/io_controlling/$state/set", "sleeping")
    pause()
    assert algo.state == "sleeping"

    pubsub.publish(f"morbidostat/{unit}/{experiment}/io_controlling/$state/set", "ready")
    pause()
    assert algo.state == "ready"


def test_old_readings_will_not_execute_io():
    algo = ControlAlgorithm(target_growth_rate=0.05, target_od=1.0, duration=60, verbose=2, unit=unit, experiment=experiment)
    algo.latest_growth_rate = 1
    algo.latest_od = 1

    algo.latest_od_timestamp = time.time() - 10 * 60
    algo.latest_growth_rate_timestamp = time.time() - 4 * 60

    assert algo.most_stale_time == algo.latest_od_timestamp

    assert isinstance(algo.run(), events.NoEvent)


def test_throughput_calculator():
    job_name = "throughput_calculating"
    pubsub.publish(f"morbidostat/{unit}/{experiment}/{job_name}/media_throughput", 0, retain=True)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/{job_name}/alt_media_throughput", 0, retain=True)

    algo = PIDMorbidostat(target_growth_rate=0.05, target_od=1.0, duration=60, verbose=2, unit=unit, experiment=experiment)
    assert algo.throughput_calculator.media_throughput == 0
    pause()
    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.08)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 1.00)
    pause()
    algo.run()

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.08)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.95)
    pause()
    algo.run()
    assert algo.throughput_calculator.media_throughput > 0
    assert algo.throughput_calculator.alt_media_throughput > 0

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.07)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.95)
    pause()
    algo.run()
    assert algo.throughput_calculator.media_throughput > 0
    assert algo.throughput_calculator.alt_media_throughput > 0

    pubsub.publish(f"morbidostat/{unit}/{experiment}/growth_rate", 0.065)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/od_filtered/135/A", 0.95)
    pause()
    algo.run()
    assert algo.throughput_calculator.media_throughput > 0
    assert algo.throughput_calculator.alt_media_throughput > 0


def test_throughput_calculator_restart():
    job_name = "throughput_calculating"

    pubsub.publish(f"morbidostat/{unit}/{experiment}/{job_name}/media_throughput", 1.0, retain=True)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/{job_name}/alt_media_throughput", 1.5, retain=True)

    target_growth_rate = 0.06
    algo = PIDMorbidostat(target_growth_rate=0.05, target_od=1.0, duration=60, verbose=2, unit=unit, experiment=experiment)
    pause()
    assert algo.throughput_calculator.media_throughput == 1.0
    assert algo.throughput_calculator.alt_media_throughput == 1.5


def test_throughput_calculator_manual_set():
    job_name = "throughput_calculating"

    pubsub.publish(f"morbidostat/{unit}/{experiment}/{job_name}/media_throughput", 1.0, retain=True)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/{job_name}/alt_media_throughput", 1.5, retain=True)
    pause()
    target_growth_rate = 0.06
    algo = PIDMorbidostat(target_growth_rate=0.05, target_od=1.0, duration=60, verbose=2, unit=unit, experiment=experiment)
    pause()
    assert algo.throughput_calculator.media_throughput == 1.0
    assert algo.throughput_calculator.alt_media_throughput == 1.5

    pubsub.publish(f"morbidostat/{unit}/{experiment}/{job_name}/alt_media_throughput/set", 0)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/{job_name}/media_throughput/set", 0)
    pause()
    assert algo.throughput_calculator.media_throughput == 0
    assert algo.throughput_calculator.alt_media_throughput == 0


def test_execute_io_action():
    pubsub.publish(f"morbidostat/{unit}/{experiment}/throughput_calculating/media_throughput", None, retain=True)
    pubsub.publish(f"morbidostat/{unit}/{experiment}/throughput_calculating/alt_media_throughput", None, retain=True)
    ca = ControlAlgorithm(verbose=2, unit=unit, experiment=experiment)
    ca.execute_io_action(media_ml=0.65, alt_media_ml=0.35, waste_ml=0.65 + 0.35)
    pause()
    assert ca.throughput_calculator.media_throughput == 0.65
    assert ca.throughput_calculator.alt_media_throughput == 0.35
