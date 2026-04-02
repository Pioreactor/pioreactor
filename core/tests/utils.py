# -*- coding: utf-8 -*-
import time
from contextlib import contextmanager
from typing import Any
from typing import Callable

from msgspec.json import decode
from pioreactor import bioreactor
from pioreactor import pubsub
from pioreactor import structs


class FakeMQTTMessageInfo:
    def __init__(self, wait_error: Exception | None = None) -> None:
        self.wait_error = wait_error
        self.wait_calls: list[float | None] = []

    def wait_for_publish(self, timeout: float | None = None) -> None:
        self.wait_calls.append(timeout)
        if self.wait_error is not None:
            raise self.wait_error


class FakeMQTTClient:
    def __init__(
        self,
        *,
        on_publish: Callable[..., Any] | None = None,
        message_info_factory: Callable[[], FakeMQTTMessageInfo] | None = None,
    ) -> None:
        self.on_publish = on_publish
        self.message_info_factory = message_info_factory or FakeMQTTMessageInfo
        self.published: list[tuple[str, Any, bool]] = []
        self.publish_calls: list[dict[str, Any]] = []
        self.callbacks: dict[str, object] = {}
        self.subscriptions: list[str] = []
        self.unsubscribed: list[str] = []
        self.shutdown_called = False

    def __enter__(self) -> "FakeMQTTClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def publish(
        self, topic: str, payload: Any = None, retain: bool = True, **kwargs: Any
    ) -> FakeMQTTMessageInfo:
        self.published.append((topic, payload, retain))
        self.publish_calls.append(
            {
                "topic": topic,
                "payload": payload,
                "retain": retain,
                "kwargs": kwargs,
            }
        )
        if self.on_publish is not None:
            self.on_publish(topic, payload, **kwargs)
        return self.message_info_factory()

    def message_callback_add(self, topic: str, callback: object) -> None:
        self.callbacks[topic] = callback

    def message_callback_remove(self, topic: str) -> None:
        self.callbacks.pop(topic, None)

    def subscribe(self, topic: str, *args: Any, **kwargs: Any) -> None:
        self.subscriptions.append(topic)

    def unsubscribe(self, topic: str) -> None:
        self.unsubscribed.append(topic)

    def shutdown(self) -> None:
        self.shutdown_called = True


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
