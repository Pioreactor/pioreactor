# -*- coding: utf-8 -*-
# test_watchdog
from __future__ import annotations

import time

import zeroconf

from pioreactor.background_jobs.leader.watchdog import WatchDog
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.whoami import get_unit_name


def test_watchdog_alerts_on_found_worker():
    experiment = "test_watchdog_alerts_on_found_worker"

    r = zeroconf.Zeroconf()

    info = zeroconf.ServiceInfo(
        "_pio-worker._tcp.local.",
        "pioreactor-worker-on-worker1._pio-worker._tcp.local.",
        addresses=["192.168.1.0"],
        server="worker1.local.",
        port=1234,
    )

    r.register_service(info)

    with collect_all_logs_of_level("NOTICE", get_unit_name(), experiment) as logs:
        with WatchDog(unit=get_unit_name(), experiment=experiment):
            time.sleep(8)

        assert len(logs) > 0
