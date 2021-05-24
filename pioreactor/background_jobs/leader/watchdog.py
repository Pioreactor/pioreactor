# -*- coding: utf-8 -*-
import os, signal, logging, json, time

import click

from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.pubsub import subscribe

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]
logger = logging.getLogger(JOB_NAME)

unit = get_unit_name()


class WatchDog(BackgroundJob):
    def __init__(self, unit, experiment):
        super(WatchDog, self).__init__(
            job_name=JOB_NAME, unit=unit, experiment=experiment
        )

        self.start_passive_listeners()

    def watch_for_lost_state(self, msg):
        if msg.payload.decode() == self.LOST:
            # TODO: this song-and-dance works for monitor, why not extend it to other jobs...

            # let's try pinging the unit a few times first:
            unit = msg.topic.split("/")[1]

            self.logger.warning(
                f"{unit} seems to be lost. Trying to re-establish connection..."
            )
            time.sleep(5)
            self.pub_client.publish(
                f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/monitor/$state/set", self.INIT
            )
            time.sleep(5)
            self.pub_client.publish(
                f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/monitor/$state/set", self.READY
            )
            time.sleep(5)

            current_state = subscribe(
                f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/monitor/$state", timeout=2
            ).payload.decode()

            if current_state == self.LOST:
                # failed, let's confirm to user
                self.logger.error(f"{unit} was lost.")
            else:
                self.logger.info(f"Update: {unit} is connected. All is well.")

    def watch_for_computer_statistics(self, msg):
        stats = json.loads(msg.payload.decode())
        unit = msg.topic.split("/")[1]

        if stats["disk_usage_percent"] >= 90:
            self.logger.warning(
                f"{unit} is running low on disk space, at {float(msg.payload)}% full."
            )

        # TODO: add other stats here

    def watch_for_new_experiment(self, msg):
        new_experiment_name = msg.payload.decode()
        self.logger.debug(f"New latest experiment in MQTT: {new_experiment_name}")

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self.watch_for_lost_state,
            "pioreactor/+/+/monitor/$state",
            allow_retained=False,
        )
        self.subscribe_and_callback(
            self.watch_for_computer_statistics,
            "pioreactor/+/+/monitor/computer_statistics",
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
    WatchDog(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)

    signal.pause()
