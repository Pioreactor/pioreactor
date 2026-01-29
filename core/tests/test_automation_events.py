# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from msgspec.json import decode
from msgspec.json import encode
from pioreactor.automations import events


ALL_EVENT_TYPES = (
    events.NoEvent,
    events.DilutionEvent,
    events.DosingStarted,
    events.DosingStopped,
    events.AddMediaEvent,
    events.AddAltMediaEvent,
    events.ChangedLedIntensity,
    events.ErrorOccurred,
    events.UpdatedHeaterDC,
)


def test_event_serialization_has_event_name() -> None:
    for event_type in ALL_EVENT_TYPES:
        event = event_type(message="hello", data={"k": 1})
        payload = decode(encode(event), type=dict[str, Any])
        assert payload["event_name"] == event_type.__struct_config__.tag
        assert payload["message"] == "hello"
        assert payload["data"] == {"k": 1}


def test_event_display_with_and_without_message() -> None:
    with_message = events.NoEvent(message="demo")
    assert with_message.display() == "NoEvent: demo"

    without_message = events.NoEvent()
    assert without_message.display() == "NoEvent"
