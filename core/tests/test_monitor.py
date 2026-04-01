# -*- coding: utf-8 -*-
# test_monitor
import time
from types import SimpleNamespace

import pytest
import zeroconf
from msgspec.json import encode
from pioreactor import bioreactor
from pioreactor import structs
from pioreactor.background_jobs.monitor import Monitor
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def pause(n=1):
    time.sleep(n * 0.5)


@pytest.mark.slow
@pytest.mark.skip()
def test_check_job_states_in_monitor() -> None:
    unit = get_unit_name()
    exp = UNIVERSAL_EXPERIMENT

    # suppose od_reading is READY when monitor starts, but isn't actually running, ex after a reboot on a worker.
    publish(
        f"pioreactor/{unit}/{get_assigned_experiment_name(unit)}/od_reading/$state",
        "ready",
        retain=True,
    )

    with Monitor(unit=unit, experiment=exp):
        pause(20)
        message = subscribe(f"pioreactor/{unit}/{get_assigned_experiment_name(unit)}/od_reading/$state")
        assert message is not None
        assert message.payload.decode() == "lost"


@pytest.mark.slow
@pytest.mark.skip()
def test_monitor_alerts_on_found_worker() -> None:
    experiment = "test_monitor_alerts_on_found_worker"

    r = zeroconf.Zeroconf()
    info = zeroconf.ServiceInfo(
        "_pio-worker._tcp.local.",
        "pioreactor-worker-on-workerX._pio-worker._tcp.local.",
        addresses=[b"\xc0\xa8\x01\x00"],  # "192.168.1.0"
        server="workerX.local.",
        port=1234,
    )

    r.register_service(info)

    with collect_all_logs_of_level("NOTICE", get_unit_name(), experiment) as logs:
        with Monitor(unit=get_unit_name(), experiment=experiment):
            time.sleep(20)

        assert len(logs) > 0

    r.unregister_service(info)


@pytest.mark.slow
@pytest.mark.skip()
def test_monitor_doesnt_alert_if_already_in_cluster() -> None:
    experiment = "test_monitor_doesnt_alert_if_already_in_cluster"

    r = zeroconf.Zeroconf()

    info = zeroconf.ServiceInfo(
        "_pio-worker._tcp.local.",
        "pioreactor-worker-on-unit2._pio-worker._tcp.local.",
        addresses=[b"\xc0\xa8\x01\x00"],
        server="unit2.local.",
        port=1234,
    )

    r.register_service(info)

    with collect_all_logs_of_level("NOTICE", get_unit_name(), experiment) as logs:
        with Monitor(unit=get_unit_name(), experiment=experiment):
            time.sleep(20)

        assert len(logs) == 1

    r.unregister_service(info)


@pytest.mark.slow
@pytest.mark.skip()
def test_monitor_projects_dosing_events_into_bioreactor() -> None:
    unit = get_unit_name()
    experiment = "test_monitor_projects_dosing_events_into_bioreactor"

    with Monitor(unit=unit, experiment=UNIVERSAL_EXPERIMENT):
        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            encode(
                structs.DosingEvent(
                    volume_change=1.5,
                    event="add_alt_media",
                    source_of_event="test",
                    timestamp=current_utc_datetime(),
                )
            ),
        )
        pause(2)

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(15.5)
    assert bioreactor.get_bioreactor_value(experiment, "alt_media_fraction") == pytest.approx(1.5 / 15.5)


@pytest.mark.slow
@pytest.mark.skip()
def test_monitor_projects_custom_add_dosing_events_into_bioreactor() -> None:
    unit = get_unit_name()
    experiment = "test_monitor_projects_custom_add_dosing_events_into_bioreactor"

    with Monitor(unit=unit, experiment=UNIVERSAL_EXPERIMENT):
        publish(
            f"pioreactor/{unit}/{experiment}/dosing_events",
            encode(
                structs.DosingEvent(
                    volume_change=1.0,
                    event="add_salty_media",
                    source_of_event="test",
                    timestamp=current_utc_datetime(),
                )
            ),
        )
        pause(2)

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(15.0)
    assert bioreactor.get_bioreactor_value(experiment, "alt_media_fraction") == pytest.approx(0.0)


def test_monitor_ignores_pump_calibration_dosing_events_for_bioreactor_projection(monkeypatch) -> None:
    unit = get_unit_name()
    experiment = "test_monitor_ignores_pump_calibration_dosing_events_for_bioreactor_projection"
    monitor = object.__new__(Monitor)
    monitor.unit = unit
    monitor.pub_client = None
    apply_calls: list[structs.DosingEvent] = []

    def fake_apply_dosing_event_to_bioreactor(
        unit: str,
        experiment: str,
        dosing_event: structs.DosingEvent,
        mqtt_client=None,
    ) -> None:
        apply_calls.append(dosing_event)

    monkeypatch.setattr(bioreactor, "apply_dosing_event_to_bioreactor", fake_apply_dosing_event_to_bioreactor)

    monitor.update_bioreactor_state_from_dosing_event(
        SimpleNamespace(
            topic=f"pioreactor/{unit}/{experiment}/dosing_events",
            payload=encode(
                structs.DosingEvent(
                    volume_change=0.4,
                    event="add_media",
                    source_of_event="pump_calibration",
                    timestamp=current_utc_datetime(),
                )
            ),
        )
    )

    assert apply_calls == []


def test_monitor_projects_non_calibration_dosing_events_into_bioreactor(monkeypatch) -> None:
    unit = get_unit_name()
    experiment = "test_monitor_projects_non_calibration_dosing_events_into_bioreactor"
    monitor = object.__new__(Monitor)
    monitor.unit = unit
    monitor.pub_client = None
    apply_calls: list[structs.DosingEvent] = []

    def fake_apply_dosing_event_to_bioreactor(
        unit: str,
        experiment: str,
        dosing_event: structs.DosingEvent,
        mqtt_client=None,
    ) -> None:
        apply_calls.append(dosing_event)

    monkeypatch.setattr(bioreactor, "apply_dosing_event_to_bioreactor", fake_apply_dosing_event_to_bioreactor)

    monitor.update_bioreactor_state_from_dosing_event(
        SimpleNamespace(
            topic=f"pioreactor/{unit}/{experiment}/dosing_events",
            payload=encode(
                structs.DosingEvent(
                    volume_change=0.4,
                    event="add_media",
                    source_of_event="test",
                    timestamp=current_utc_datetime(),
                )
            ),
        )
    )

    assert len(apply_calls) == 1
    assert apply_calls[0].source_of_event == "test"
