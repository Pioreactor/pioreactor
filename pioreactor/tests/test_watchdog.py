# -*- coding: utf-8 -*-
# test_watchdog
from __future__ import annotations

import time

import pytest
import zeroconf

from pioreactor.background_jobs.leader.watchdog import WatchDog
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.whoami import get_unit_name


@pytest.mark.xfail()
def test_watchdog_alerts_on_found_worker() -> None:
    experiment = "test_watchdog_alerts_on_found_worker"

    r = zeroconf.Zeroconf()

    info = zeroconf.ServiceInfo(
        "_pio-worker._tcp.local.",
        "pioreactor-worker-on-workerX._pio-worker._tcp.local.",
        addresses=["192.168.1.0"],
        server="workerX.local.",
        port=1234,
    )

    r.register_service(info)

    with collect_all_logs_of_level("NOTICE", get_unit_name(), experiment) as logs:
        with WatchDog(unit=get_unit_name(), experiment=experiment):
            time.sleep(20)

        assert len(logs) > 0

    r.unregister_service(info)


def test_watchdog_doesnt_alert_if_already_in_cluster() -> None:
    experiment = "test_watchdog_doesnt_alert_if_already_in_cluster"

    r = zeroconf.Zeroconf()

    info = zeroconf.ServiceInfo(
        "_pio-worker._tcp.local.",
        "pioreactor-worker-on-unit2._pio-worker._tcp.local.",
        addresses=["192.168.1.0"],
        server="unit2.local.",
        port=1234,
    )

    r.register_service(info)

    with collect_all_logs_of_level("NOTICE", get_unit_name(), experiment) as logs:
        with WatchDog(unit=get_unit_name(), experiment=experiment):
            time.sleep(20)

        assert len(logs) == 0

    r.unregister_service(info)
