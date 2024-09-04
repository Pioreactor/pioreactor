# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time

import click

from pioreactor.background_jobs.base import LongRunningBackgroundJob
from pioreactor.cluster_management import get_workers_in_inventory
from pioreactor.config import get_leader_hostname
from pioreactor.pubsub import subscribe
from pioreactor.types import MQTTMessage
from pioreactor.utils.networking import discover_workers_on_network
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


class WatchDog(LongRunningBackgroundJob):
    job_name = "watchdog"

    def __init__(self, unit: str, experiment: str) -> None:
        super(WatchDog, self).__init__(unit=unit, experiment=experiment)

        self.start_passive_listeners()

    def on_init_to_ready(self) -> None:
        threading.Thread(target=self.announce_new_workers, daemon=True).start()

    def announce_new_workers(self) -> None:
        time.sleep(10)  # wait for the web server to be available
        for worker in discover_workers_on_network():
            # not in current cluster, and not leader
            if (worker not in get_workers_in_inventory()) and (worker != get_leader_hostname()):
                # is there an MQTT state for this worker?
                # a new worker doesn't have the leader_address, so it won't connect to the leaders MQTT.
                result = subscribe(
                    f"pioreactor/{worker}/{UNIVERSAL_EXPERIMENT}/monitor/$state",
                    timeout=3,
                    name=self.job_name,
                    retries=1,
                )
                if result is None or result.payload.decode() == self.LOST:
                    self.logger.notice(  # type: ignore
                        f"Pioreactor worker, {worker}, is available to be added to your cluster."
                    )

    def watch_for_lost_state(self, state_message: MQTTMessage) -> None:
        unit = state_message.topic.split("/")[1]

        # ignore if leader is "lost"
        if (
            (state_message.payload.decode() == self.LOST)
            and (unit != self.unit)
            and (unit in get_workers_in_inventory())
        ):
            self.logger.warning(f"{unit} seems to be lost.")

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self.watch_for_lost_state,
            "pioreactor/+/+/monitor/$state",
            allow_retained=False,
        )


@click.command(name="watchdog")
def click_watchdog() -> None:
    """
    (leader only) Start the watchdog on the leader
    """
    import os

    os.nice(1)

    wd = WatchDog(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
    wd.block_until_disconnected()
