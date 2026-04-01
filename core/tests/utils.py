# -*- coding: utf-8 -*-
import time
from contextlib import contextmanager
from typing import Callable

from msgspec.json import decode
from pioreactor import bioreactor
from pioreactor import pubsub
from pioreactor import structs


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0, check_interval: float = 0.05) -> bool:
    """
    Poll `predicate` until it returns True or timeout expires.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            # predicates used in tests may raise intermittently while state warms up
            pass
        time.sleep(check_interval)
    return False


@contextmanager
def dosing_events_to_bioreactor_projector(unit: str, experiment: str):
    """
    Test-only helper that mirrors dosing events into shared bioreactor state.

    This replicates the monitor job's dosing_events -> bioreactor projection without
    bringing up the full monitor background job and its unrelated side effects.
    """

    listener_client = None
    publisher_client = pubsub.create_client(client_id=f"{unit}_{experiment}_bioreactor_projector_pub")

    def on_message(message) -> None:
        assert publisher_client is not None
        dosing_event = decode(message.payload, type=structs.DosingEvent)
        if dosing_event.source_of_event == "pump_calibration":
            return
        bioreactor.apply_dosing_event_to_bioreactor(
            unit,
            experiment,
            dosing_event,
            mqtt_client=publisher_client,
        )

    listener_client = pubsub.subscribe_and_callback(
        on_message,
        f"pioreactor/{unit}/{experiment}/dosing_events",
        allow_retained=False,
        client_id=f"{unit}_{experiment}_bioreactor_projector",
    )

    try:
        yield listener_client
    finally:
        listener_client.shutdown()
        publisher_client.shutdown()
