# -*- coding: utf-8 -*-
"""Subprocess fixture: real job lifecycle with fake hardware and in-memory MQTT delivery."""
import os
import signal
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

assert os.environ.get("TESTING") == "1"
from pioreactor.actions import pump as pumps
from pioreactor.background_jobs.dosing_automation import DosingAutomationJob
from pioreactor.background_jobs import base
from pioreactor.config import config
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.pwm import PWM
from tests.utils import FakeMQTTClient


def configure(root: str) -> None:
    config.set("storage", "temporary_cache", str(Path(root) / "temporary.sqlite"))
    config.set("storage", "persistent_cache", str(Path(root) / "persistent.sqlite"))


def child(mode: str, root: str, stop: str) -> None:
    configure(root)
    logger = MagicMock()
    logger.info.side_effect = lambda message, *a, **kw: print(message, flush=True)
    base.create_logger = lambda *a, **kw: logger
    client = FakeMQTTClient()

    def deliver(topic: str, payload: object, **kwargs: object) -> None:
        if topic in client.callbacks:
            client.callbacks[topic](client, None, SimpleNamespace(payload=payload, retain=False))

    client.on_publish = deliver
    original_cleanup = PWM.clean_up

    def delayed_cleanup(self: PWM) -> None:
        # Force scheduling at the ownership boundary: output stopped, lock still held.
        if threading.current_thread() is not threading.main_thread():
            print("ENTER_CLEANUP", flush=True)
            time.sleep(0.75)
        original_cleanup(self)
        print("CLEANUP_DONE", flush=True)

    PWM.clean_up = delayed_cleanup

    if mode == "standalone":

        def interrupt_action() -> None:
            deadline = time.monotonic() + 5
            pin = pumps._get_pin("waste_pump")
            while time.monotonic() < deadline:
                with local_intermittent_storage("pwm_dc") as cache:
                    if cache.get(pin, 0) > 0:
                        if stop == "mqtt":
                            client.publish("pioreactor/probe/probe/remove_waste/$state/set", b"disconnected")
                        else:
                            os.kill(os.getpid(), getattr(signal, stop))
                        return
                time.sleep(0.01)
            raise RuntimeError("Standalone pump did not start")

        interrupter = threading.Thread(target=interrupt_action)
        interrupter.start()
        try:
            pumps.remove_waste(
                unit="probe", experiment="probe", duration=10, mqtt_client=client, logger=logger
            )
        except KeyboardInterrupt:
            pass
        finally:
            interrupter.join(timeout=6)
        return

    class Probe(DosingAutomationJob):
        automation_name = "shutdown_probe"

        def _create_pub_client(self) -> FakeMQTTClient:
            return client

        def _create_sub_client(self) -> FakeMQTTClient:
            return FakeMQTTClient()

        def _start_general_passive_listeners(self) -> None:
            pass

        def execute(self) -> None:
            pumps.remove_waste(
                unit=self.unit,
                experiment=self.experiment,
                duration=10,
                mqtt_client=self.pub_client,
                logger=self.logger,
                cancel_event=self._stop_pumping_event,
            )

    job = Probe(
        unit="probe", experiment="probe", current_volume_ml=10, efflux_tube_volume_ml=10, alt_media_fraction=0
    )
    if mode.startswith("event"):
        job.trigger_run_once_from_event()
    else:
        job._set_periodic_timer(1, skip_first_run=False, run_after_seconds=0)

    deadline = time.monotonic() + 5
    pin = pumps._get_pin("waste_pump")
    while time.monotonic() < deadline:
        with local_intermittent_storage("pwm_dc") as cache:
            if cache.get(pin, 0) > 0:
                break
        time.sleep(0.01)
    else:
        raise RuntimeError("Pump did not start")
    print(f"SEND_{stop}", flush=True)
    try:
        if stop == "mqtt":
            job.set_state(job.DISCONNECTED)
            job.clean_up()
        else:
            os.kill(os.getpid(), getattr(signal, stop))
        job.block_until_disconnected()
    except KeyboardInterrupt:
        pass
    print("MAIN_EXIT", flush=True)


if __name__ == "__main__":
    child(*sys.argv[1:])
