# -*- coding: utf-8 -*-
from threading import Event
from threading import Thread
from types import SimpleNamespace
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from msgspec.json import encode
from pioreactor import structs
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.pubsub import Client
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils.timing import current_utc_datetime


def test_growth_rate_calculator_subscribes_to_od_and_dosing_on_its_existing_client() -> None:
    od_topic = "pioreactor/unit/experiment/od_reading/ods"
    dosing_topic = "pioreactor/unit/experiment/dosing_events"

    with (
        patch(
            "pioreactor.background_jobs.growth_rate_calculating._should_use_fused_od",
            return_value=False,
        ),
        patch.object(GrowthRateCalculator, "subscribe_and_callback", autospec=True) as subscribe,
    ):
        with GrowthRateCalculator(unit="unit", experiment="experiment") as calculator:
            matching_calls = [
                subscription
                for subscription in subscribe.call_args_list
                if len(subscription.args) >= 3 and subscription.args[2] == [od_topic, dosing_topic]
            ]

            assert calculator.state == calculator.READY
            assert len(matching_calls) == 1
            assert matching_calls[0].args[0] is calculator
            assert matching_calls[0].args[1] == calculator._growth_rate_event_messages.put
            assert matching_calls[0].kwargs == {"allow_retained": False}


def test_growth_rate_calculator_stream_preserves_raw_event_order_and_skip_contract() -> None:
    timestamp = current_utc_datetime()
    readings = [
        structs.ODReadings(
            timestamp=timestamp,
            ods={
                "1": structs.RawODReading(
                    timestamp=timestamp,
                    angle="90",
                    od=od,
                    channel="1",
                    ir_led_intensity=70.0,
                )
            },
        )
        for od in (0.0, 0.1, 0.2)
    ]
    dosing_event = structs.DosingEvent(
        volume_change=1.0,
        event="add_media",
        source_of_event="test",
        timestamp=timestamp,
    )
    od_topic = "pioreactor/unit/experiment/od_reading/ods"
    dosing_topic = "pioreactor/unit/experiment/dosing_events"

    with (
        patch(
            "pioreactor.background_jobs.growth_rate_calculating._should_use_fused_od",
            return_value=False,
        ),
        patch.object(GrowthRateCalculator, "subscribe_and_callback", autospec=True),
    ):
        with GrowthRateCalculator(unit="unit", experiment="experiment") as calculator:
            calculator._growth_rate_event_messages.put(
                SimpleNamespace(topic=od_topic, payload=encode(readings[0]), retain=False)
            )
            calculator._growth_rate_event_messages.put(
                SimpleNamespace(topic=dosing_topic, payload=encode(dosing_event), retain=False)
            )
            for reading in readings[1:]:
                calculator._growth_rate_event_messages.put(
                    SimpleNamespace(topic=od_topic, payload=encode(reading), retain=False)
                )

            events = calculator.stream_mqtt_growth_rate_events(skip_first_od_observations=1)

            assert next(events) == dosing_event
            assert next(events) == readings[1]
            assert next(events) == readings[2]

            calculator._blocking_event.set()
            with pytest.raises(StopIteration):
                next(events)


def test_growth_rate_calculator_stream_preserves_fused_od_readings_contract() -> None:
    timestamp = current_utc_datetime()
    fused = structs.ODFused(od_fused=0.42, timestamp=timestamp)
    od_topic = "pioreactor/unit/experiment/od_reading/od_fused"

    with (
        patch(
            "pioreactor.background_jobs.growth_rate_calculating._should_use_fused_od",
            return_value=True,
        ),
        patch.object(GrowthRateCalculator, "subscribe_and_callback", autospec=True),
    ):
        with GrowthRateCalculator(unit="unit", experiment="experiment") as calculator:
            calculator._growth_rate_event_messages.put(
                SimpleNamespace(topic=od_topic, payload=encode(fused), retain=False)
            )
            events = calculator.stream_mqtt_growth_rate_events(skip_first_od_observations=0)

            reading = next(events)

            assert reading.timestamp == timestamp
            assert reading.ods["1"] == structs.RawODReading(
                timestamp=timestamp,
                angle="90",
                od=0.42,
                channel="1",
                ir_led_intensity=0.0,
            )


def test_growth_rate_calculator_stream_recovers_from_malformed_payloads() -> None:
    timestamp = current_utc_datetime()
    dosing_event = structs.DosingEvent(
        volume_change=1.0,
        event="add_media",
        source_of_event="test",
        timestamp=timestamp,
    )
    dosing_topic = "pioreactor/unit/experiment/dosing_events"

    with (
        patch(
            "pioreactor.background_jobs.growth_rate_calculating._should_use_fused_od",
            return_value=False,
        ),
        patch.object(GrowthRateCalculator, "subscribe_and_callback", autospec=True),
    ):
        with GrowthRateCalculator(unit="unit", experiment="experiment") as calculator:
            calculator._growth_rate_event_messages.put(
                SimpleNamespace(topic=dosing_topic, payload=b"not-json", retain=False)
            )
            calculator._growth_rate_event_messages.put(
                SimpleNamespace(topic=dosing_topic, payload=encode(dosing_event), retain=False)
            )

            with patch.object(calculator.logger, "warning") as warning:
                events = calculator.stream_mqtt_growth_rate_events(skip_first_od_observations=0)

                assert next(events) == dosing_event
                warning.assert_called_once()


def test_growth_rate_calculator_stream_stop_unblocks_without_closing_shared_client() -> None:
    with (
        patch(
            "pioreactor.background_jobs.growth_rate_calculating._should_use_fused_od",
            return_value=False,
        ),
        patch.object(GrowthRateCalculator, "subscribe_and_callback", autospec=True),
    ):
        calculator = GrowthRateCalculator(unit="unit", experiment="experiment")

    finished = Event()
    errors: list[BaseException] = []
    events = calculator.stream_mqtt_growth_rate_events(skip_first_od_observations=0)

    def consume_one_event() -> None:
        try:
            next(events)
        except StopIteration:
            pass
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    with patch.object(calculator.sub_client, "shutdown") as shutdown:
        with calculator:
            consumer = Thread(target=consume_one_event)
            consumer.start()

            calculator._blocking_event.set()

            assert finished.wait(timeout=0.5)
            consumer.join()
            assert errors == []
            shutdown.assert_not_called()

        shutdown.assert_called_once_with()


def test_subscribe_and_callback_filters_retained_messages_and_resubscribes_after_reconnect() -> None:
    client = MagicMock(spec=Client)
    captured_callbacks = {}
    received_messages = []

    def create_client(**kwargs):
        captured_callbacks.update(kwargs)
        kwargs["on_connect"](client, kwargs["userdata"])
        kwargs["on_subscribe"](client, kwargs["userdata"], 1, (2,))
        return client

    with patch("pioreactor.pubsub.create_client", side_effect=create_client):
        returned_client = subscribe_and_callback(
            received_messages.append,
            "test/topic",
            allow_retained=False,
        )

    captured_callbacks["on_connect"](client, captured_callbacks["userdata"])
    retained_message = SimpleNamespace(retain=True)
    live_message = SimpleNamespace(retain=False)
    captured_callbacks["on_message"](client, captured_callbacks["userdata"], retained_message)
    captured_callbacks["on_message"](client, captured_callbacks["userdata"], live_message)

    assert returned_client is client
    assert received_messages == [live_message]
    assert client.subscribe.call_args_list == [
        call([("test/topic", 2)]),
        call([("test/topic", 2)]),
    ]
