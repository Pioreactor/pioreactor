# -*- coding: utf-8 -*-
from __future__ import annotations

import time

import click

from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.pubsub import subscribe
from pioreactor.types import MQTTMessage
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


class WatchDog(BackgroundJob):
    def __init__(self, unit: str, experiment: str) -> None:
        super(WatchDog, self).__init__(
            job_name="watchdog", unit=unit, experiment=experiment
        )

        self.start_passive_listeners()

    def watch_for_lost_state(self, state_message: MQTTMessage) -> None:
        # generally, I hate this code below...

        unit = state_message.topic.split("/")[1]

        # ignore if leader is "lost"
        if (state_message.payload.decode() == self.LOST) and (unit != self.unit):

            # TODO: this song-and-dance works for monitor, why not extend it to other jobs...

            self.logger.warning(
                f"{unit} seems to be lost. Trying to re-establish connection..."
            )
            time.sleep(5)

            if self.state != self.READY:
                # when the entire Rpi shuts down, ex via sudo reboot, monitor can publish a lost. This code will halt the shutdown.
                # let's return early.
                return

            self.pub_client.publish(
                f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/monitor/$state/set", self.READY
            )
            time.sleep(20)

            if self.state != self.READY:
                # when the entire Rpi shuts down, ex via sudo reboot, monitor can publish a lost. This code will halt the shutdown.
                # let's return early.
                return

            msg = subscribe(  # I don't think this can be self.sub_client because we are in a callback.
                f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/monitor/$state",
                timeout=15,
                name=self.job_name,
            )
            if msg is None:
                return

            current_state = msg.payload.decode()

            if current_state == self.LOST:
                # failed, let's confirm to user
                self.logger.error(f"{unit} was lost.")
            else:
                self.logger.info(f"Update: {unit} is connected. All is well.")

    def watch_for_new_experiment(self, msg: MQTTMessage) -> None:
        new_experiment_name = msg.payload.decode()
        self.logger.debug(
            f"New latest experiment detected in MQTT: {new_experiment_name}"
        )
        self.logger.info(f"New experiment created: {new_experiment_name}")

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self.watch_for_lost_state,
            "pioreactor/+/+/monitor/$state",
            allow_retained=False,
        )
        self.subscribe_and_callback(
            self.watch_for_new_experiment,
            "pioreactor/latest_experiment",
            allow_retained=False,
        )


@click.command(name="watchdog")
def click_watchdog():
    """
    Start the watchdog on the leader
    """
    import os

    os.nice(1)

    wd = WatchDog(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
    wd.block_until_disconnected()
