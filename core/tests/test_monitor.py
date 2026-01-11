# -*- coding: utf-8 -*-
# test_monitor
import time

import pytest
import zeroconf
from pioreactor.background_jobs.monitor import Monitor
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
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
