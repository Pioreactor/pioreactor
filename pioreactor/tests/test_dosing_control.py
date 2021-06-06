# -*- coding: utf-8 -*-
import time

from pioreactor.automations.dosing.morbidostat import Morbidostat
from pioreactor.automations.dosing.pid_morbidostat import PIDMorbidostat
from pioreactor.automations.dosing.pid_turbidostat import PIDTurbidostat
from pioreactor.automations.dosing.silent import Silent
from pioreactor.automations.dosing.turbidostat import Turbidostat

from pioreactor.background_jobs.dosing_control import DosingController
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.automations import events
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor import pubsub

unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.5)


def test_silent_automation():
    algo = Silent(volume=None, duration=60, unit=unit, experiment=experiment)
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.0}',
    )
    pause()
    assert isinstance(algo.run(), events.NoEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.02}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.1}',
    )
    pause()
    assert isinstance(algo.run(), events.NoEvent)
    # algo.set_state("disconnected")


def test_turbidostat_automation():
    target_od = 1.0
    algo = Turbidostat(
        target_od=target_od, duration=60, volume=0.25, unit=unit, experiment=experiment
    )

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.98}',
    )
    pause()
    assert isinstance(algo.run(), events.NoEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.0}',
    )
    pause()
    assert isinstance(algo.run(), events.DilutionEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.01}',
    )
    pause()
    assert isinstance(algo.run(), events.DilutionEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.99}',
    )
    pause()
    assert isinstance(algo.run(), events.NoEvent)
    algo.set_state("disconnected")


def test_pid_turbidostat_automation():

    target_od = 2.4
    algo = PIDTurbidostat(
        target_od=target_od, duration=20, unit=unit, experiment=experiment
    )

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 2.6}',
    )
    pause()
    e = algo.run()
    assert isinstance(e, events.DilutionEvent)
    assert e.volume_to_cycle > 1.0

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 2.8}',
    )
    pause()
    e = algo.run()
    assert isinstance(e, events.DilutionEvent)
    assert e.volume_to_cycle > 1.0
    algo.set_state("disconnected")


def test_morbidostat_automation():
    target_od = 1.0
    algo = Morbidostat(
        target_od=target_od, duration=60, volume=0.25, unit=unit, experiment=experiment
    )

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.95}',
    )
    pause()
    assert isinstance(algo.run(), events.NoEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.99}',
    )
    pause()
    assert isinstance(algo.run(), events.DilutionEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.05}',
    )
    pause()
    assert isinstance(algo.run(), events.AltMediaEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.03}',
    )
    pause()
    assert isinstance(algo.run(), events.DilutionEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.04}',
    )
    pause()
    assert isinstance(algo.run(), events.AltMediaEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.01}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.99}',
    )
    pause()
    assert isinstance(algo.run(), events.DilutionEvent)
    algo.set_state("disconnected")


def test_pid_morbidostat_automation():
    target_growth_rate = 0.09
    algo = PIDMorbidostat(
        target_od=1.0,
        target_growth_rate=target_growth_rate,
        duration=60,
        unit=unit,
        experiment=experiment,
    )

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.08}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.5}',
    )
    pause()
    assert isinstance(algo.run(), events.NoEvent)
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.08}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.95}',
    )
    pause()
    assert isinstance(algo.run(), events.AltMediaEvent)
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.07}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.95}',
    )
    pause()
    assert isinstance(algo.run(), events.AltMediaEvent)
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.065}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.95}',
    )
    pause()
    assert isinstance(algo.run(), events.AltMediaEvent)
    algo.set_state("disconnected")


def test_changing_morbidostat_parameters_over_mqtt():

    target_growth_rate = 0.05
    algo = PIDMorbidostat(
        target_growth_rate=target_growth_rate,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.target_growth_rate == target_growth_rate
    pause()
    new_target = 0.07
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_automation/target_growth_rate/set",
        new_target,
    )
    pause()
    assert algo.target_growth_rate == new_target
    assert algo.pid.pid.setpoint == new_target
    algo.set_state("disconnected")


def test_changing_turbidostat_params_over_mqtt():

    og_volume = 0.5
    og_target_od = 1.0
    algo = PIDTurbidostat(
        volume=og_volume,
        target_od=og_target_od,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.volume == og_volume

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.05}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.0}',
    )
    pause()
    algo.run()

    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/volume/set", 1.0)
    pause()

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.05}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.0}',
    )
    algo.run()

    assert algo.volume == 1.0

    new_od = 1.5
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_automation/target_od/set", new_od
    )
    pause()
    assert algo.target_od == new_od
    assert algo.pid.pid.setpoint == new_od
    assert algo.min_od == 0.75 * new_od
    algo.set_state("disconnected")


def test_changing_parameters_over_mqtt_with_unknown_parameter():

    algo = DosingAutomation(
        target_growth_rate=0.05,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/garbage/set", 0.07)
    pause()
    algo.set_state("disconnected")


def test_pause_in_dosing_automation():

    algo = DosingAutomation(
        target_growth_rate=0.05,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_automation/$state/set", "sleeping"
    )
    pause()
    assert algo.state == "sleeping"

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_automation/$state/set", "ready"
    )
    pause()
    assert algo.state == "ready"
    algo.set_state("disconnected")


def test_pause_in_dosing_control_also_pauses_automation():

    algo = DosingController(
        "turbidostat",
        target_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    )
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_control/$state/set", "sleeping"
    )
    pause()
    assert algo.state == "sleeping"
    assert algo.dosing_automation_job.state == "sleeping"

    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_control/$state/set", "ready")
    pause()
    assert algo.state == "ready"
    assert algo.dosing_automation_job.state == "ready"
    algo.set_state("disconnected")


def test_old_readings_will_not_execute_io():
    algo = DosingAutomation(
        target_growth_rate=0.05,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    algo.latest_growth_rate = 1
    algo.latest_od = 1

    algo.latest_od_timestamp = time.time() - 10 * 60
    algo.latest_growth_rate_timestamp = time.time() - 4 * 60

    assert algo.most_stale_time == algo.latest_od_timestamp

    assert isinstance(algo.run(), events.NoEvent)
    algo.set_state("disconnected")


def test_throughput_calculator():
    job_name = "throughput_calculating"
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/{job_name}/media_throughput", 0, retain=True
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/{job_name}/alt_media_throughput", 0, retain=True
    )

    algo = PIDMorbidostat(
        target_growth_rate=0.05,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.throughput_calculator.media_throughput == 0
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.08}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.0}',
    )
    pause()
    algo.run()

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.08}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.95}',
    )
    pause()
    algo.run()
    assert algo.throughput_calculator.media_throughput > 0
    assert algo.throughput_calculator.alt_media_throughput > 0

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.07}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.95}',
    )
    pause()
    algo.run()
    assert algo.throughput_calculator.media_throughput > 0
    assert algo.throughput_calculator.alt_media_throughput > 0

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.065}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.95}',
    )
    pause()
    algo.run()
    assert algo.throughput_calculator.media_throughput > 0
    assert algo.throughput_calculator.alt_media_throughput > 0
    algo.set_state("disconnected")


def test_throughput_calculator_restart():
    job_name = "throughput_calculating"

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/{job_name}/media_throughput", 1.0, retain=True
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/{job_name}/alt_media_throughput",
        1.5,
        retain=True,
    )

    algo = PIDMorbidostat(
        target_growth_rate=0.06,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    pause()
    assert algo.throughput_calculator.media_throughput == 1.0
    assert algo.throughput_calculator.alt_media_throughput == 1.5
    algo.set_state("disconnected")


def test_throughput_calculator_manual_set():
    job_name = "throughput_calculating"

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/{job_name}/media_throughput", 1.0, retain=True
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/{job_name}/alt_media_throughput",
        1.5,
        retain=True,
    )
    pause()
    algo = PIDMorbidostat(
        target_growth_rate=0.05,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    pause()
    assert algo.throughput_calculator.media_throughput == 1.0
    assert algo.throughput_calculator.alt_media_throughput == 1.5

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/{job_name}/alt_media_throughput/set", 0
    )
    pubsub.publish(f"pioreactor/{unit}/{experiment}/{job_name}/media_throughput/set", 0)
    pause()
    assert algo.throughput_calculator.media_throughput == 0
    assert algo.throughput_calculator.alt_media_throughput == 0
    algo.set_state("disconnected")


def test_execute_io_action():
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/throughput_calculating/media_throughput",
        None,
        retain=True,
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/throughput_calculating/alt_media_throughput",
        None,
        retain=True,
    )
    ca = DosingAutomation(unit=unit, experiment=experiment)
    ca.execute_io_action(media_ml=0.65, alt_media_ml=0.35, waste_ml=0.65 + 0.35)
    pause()
    assert ca.throughput_calculator.media_throughput == 0.65
    assert ca.throughput_calculator.alt_media_throughput == 0.35

    ca.execute_io_action(media_ml=0.15, alt_media_ml=0.15, waste_ml=0.3)
    pause()
    assert ca.throughput_calculator.media_throughput == 0.80
    assert ca.throughput_calculator.alt_media_throughput == 0.50

    ca.execute_io_action(media_ml=1.0, alt_media_ml=0, waste_ml=1)
    pause()
    assert ca.throughput_calculator.media_throughput == 1.80
    assert ca.throughput_calculator.alt_media_throughput == 0.50

    ca.execute_io_action(media_ml=0.0, alt_media_ml=1.0, waste_ml=1)
    pause()
    assert ca.throughput_calculator.media_throughput == 1.80
    assert ca.throughput_calculator.alt_media_throughput == 1.50
    ca.set_state("disconnected")


def test_execute_io_action2():
    # regression test
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/alt_media_calculating/alt_media_fraction",
        None,
        retain=True,
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/throughput_calculating/media_throughput",
        None,
        retain=True,
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/throughput_calculating/alt_media_throughput",
        None,
        retain=True,
    )

    ca = DosingAutomation(unit=unit, experiment=experiment)
    ca.execute_io_action(media_ml=1.25, alt_media_ml=0.01, waste_ml=1.26)
    pause()
    assert ca.throughput_calculator.media_throughput == 1.25
    assert ca.throughput_calculator.alt_media_throughput == 0.01
    ca.set_state("disconnected")


def test_duration_and_timer():
    algo = PIDMorbidostat(
        target_od=1.0,
        target_growth_rate=0.01,
        duration=5 / 60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.latest_event is None
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.08}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.5}',
    )
    time.sleep(10)
    pause()
    assert isinstance(algo.latest_event, events.NoEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.08}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.95}',
    )
    time.sleep(10)
    pause()
    assert isinstance(algo.latest_event, events.AltMediaEvent)
    algo.set_state("disconnected")


def test_changing_duration_over_mqtt():
    algo = PIDMorbidostat(
        target_od=1.0,
        target_growth_rate=0.01,
        duration=5 / 60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.latest_event is None
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 0.08}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 0.5}',
    )
    time.sleep(10)

    assert isinstance(algo.latest_event, events.NoEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_automation/duration/set", 60 / 60
    )
    time.sleep(10)
    assert algo.timer_thread.interval == 60
    algo.set_state("disconnected")


def test_changing_algo_over_mqtt_solo():

    algo = DosingController(
        "turbidostat",
        target_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    )
    assert algo.dosing_automation == "turbidostat"
    assert isinstance(algo.dosing_automation_job, Turbidostat)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_control/dosing_automation/set",
        '{"dosing_automation": "pid_morbidostat", "duration": 60, "target_od": 1.0, "target_growth_rate": 0.07}',
    )
    time.sleep(8)
    assert algo.dosing_automation == "pid_morbidostat"
    assert isinstance(algo.dosing_automation_job, PIDMorbidostat)
    assert algo.dosing_automation_job.target_growth_rate == 0.07
    algo.set_state("disconnected")


def test_changing_algo_over_mqtt_when_it_fails_will_rollback():

    algo = DosingController(
        "turbidostat",
        target_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    )
    assert algo.dosing_automation == "turbidostat"
    assert isinstance(algo.dosing_automation_job, Turbidostat)
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_control/dosing_automation/set",
        '{"dosing_automation": "pid_morbidostat", "duration": 60}',
    )
    time.sleep(8)
    assert algo.dosing_automation == "turbidostat"
    assert isinstance(algo.dosing_automation_job, Turbidostat)
    assert algo.dosing_automation_job.target_od == 1.0
    algo.set_state("disconnected")


def test_changing_algo_over_mqtt_will_not_produce_two_dosing_jobs():
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/throughput_calculating/media_throughput",
        None,
        retain=True,
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/throughput_calculating/alt_media_throughput",
        None,
        retain=True,
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/alt_media_calculating/alt_media_fraction",
        None,
        retain=True,
    )

    algo = DosingController(
        "pid_turbidostat",
        volume=1.0,
        target_od=0.4,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.dosing_automation == "pid_turbidostat"
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_control/dosing_automation/set",
        '{"dosing_automation": "turbidostat", "duration": 60, "target_od": 1.0, "volume": 1.0, "skip_first_run": 1}',
    )
    time.sleep(
        10
    )  # need to wait for all jobs to disconnect correctly and threads to join.
    assert isinstance(algo.dosing_automation_job, Turbidostat)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        '{"growth_rate": 1.0}',
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/0",
        '{"od_filtered": 1.0}',
    )
    pause()

    # note that we manually run, as we have skipped the first run in the json
    algo.dosing_automation_job.run()
    time.sleep(5)
    assert algo.dosing_automation_job.throughput_calculator.media_throughput == 1.0

    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/target_od/set", 1.5)
    pause()
    pause()
    assert algo.dosing_automation_job.target_od == 1.5
    algo.set_state("disconnected")


def test_changing_algo_over_mqtt_with_wrong_type_is_okay():
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/throughput_calculating/media_throughput",
        None,
        retain=True,
    )

    algo = DosingController(
        "pid_turbidostat",
        volume=1.0,
        target_od=0.4,
        duration=2 / 60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.dosing_automation == "pid_turbidostat"
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_control/dosing_automation/set",
        '{"dosing_automation": "pid_turbidostat", "duration": "60", "target_od": "1.0", "volume": "1.0"}',
    )
    time.sleep(
        7
    )  # need to wait for all jobs to disconnect correctly and threads to join.
    assert isinstance(algo.dosing_automation_job, PIDTurbidostat)
    assert algo.dosing_automation_job.target_od == 1.0
    algo.set_state("disconnected")


def test_disconnect_cleanly():

    algo = DosingController(
        "turbidostat",
        target_od=1.0,
        duration=50,
        unit=unit,
        volume=1.0,
        experiment=experiment,
    )
    assert algo.dosing_automation == "turbidostat"
    assert isinstance(algo.dosing_automation_job, Turbidostat)
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_control/$state/set", "disconnected"
    )
    time.sleep(10)
    algo.set_state("disconnected")


def test_custom_class_will_register_and_run():
    class NaiveTurbidostat(DosingAutomation):

        key = "naive_turbidostat"

        def __init__(self, target_od, **kwargs):
            super(NaiveTurbidostat, self).__init__(**kwargs)
            self.target_od = target_od

        def execute(self):
            if self.latest_od > self.target_od:
                self.execute_io_action(media_ml=1.0, waste_ml=1.0)

    DosingController(
        "naive_turbidostat",
        target_od=2.0,
        duration=10,
        unit=get_unit_name(),
        experiment=get_latest_experiment_name(),
    )


def test_what_happens_when_no_od_data_is_coming_in():

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate", None
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered/135/0", None
    )

    algo = Turbidostat(
        target_od=0.1, duration=40 / 60, volume=0.25, unit=unit, experiment=experiment
    )
    pause()
    event = algo.run()
    assert isinstance(event, events.NoEvent)
    assert "Waited too long on sensor data. Skipping this run" in event.message
