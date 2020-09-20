# -*- coding: utf-8 -*-

import pytest

from morbidostat.long_running.io_controlling import io_controlling, Events
from paho.mqtt import subscribe


class MockMQTTMsg:
    def __init__(self, topic, payload):
        self.payload = payload
        self.topic = topic


class MockMsgBroker:
    def __init__(self, *list_of_msgs):
        self.list_of_msgs = list_of_msgs
        self.counter = 0
        self.callbacks = []

    def next(self):
        msg = self.list_of_msgs[self.counter]
        self.counter += 1
        if self.counter > len(self.list_of_msgs):
            raise StopIteration

        for f, topics in self.callbacks:
            if msg.topic in topics:
                f()

        return msg

    def _add_callback(self, func, topics):
        self.callbacks.append([func, topics])

    def subscribe(self, *args, **kwargs):
        topics = args[0]
        while True:
            msg = self.next()
            if msg.topic in topics:
                return msg

    def callback(self, func, topics, hostname):
        self._add_callback(func, topics)
        return


def test_silent_algorithm(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/growth_rate", "0.01"),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", "1.0"),
        MockMQTTMsg("morbidostat/_testing/growth_rate", "0.02"),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", "1.1"),
    )

    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)
    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)

    io = io_controlling("silent", None, 0.001, 0)
    assert next(io) == Events.NO_EVENT
    assert next(io) == Events.NO_EVENT


def test_turbidostat_algorithm(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 0.98),
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 1.0),
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 1.01),
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 0.99),
    )

    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)
    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)

    target_od = 1.0
    algo = io_controlling("turbidostat", target_od=target_od, duration=0.001, volume=0.25)

    assert next(algo) == Events.NO_EVENT
    assert next(algo) == Events.DILUTION_EVENT
    assert next(algo) == Events.DILUTION_EVENT
    assert next(algo) == Events.NO_EVENT


def test_morbidostat_algorithm(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 0.95),
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 0.99),
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 1.05),
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 1.03),
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 1.04),
        MockMQTTMsg("morbidostat/_testing/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/od_filtered/135", 0.99),
    )

    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)
    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)

    target_od = 1.0
    algo = io_controlling("morbidostat", target_od=target_od, duration=0.001, volume=0.25)

    assert next(algo) == Events.NO_EVENT
    assert next(algo) == Events.DILUTION_EVENT
    assert next(algo) == Events.ALT_MEDIA_EVENT
    assert next(algo) == Events.DILUTION_EVENT
    assert next(algo) == Events.ALT_MEDIA_EVENT
    assert next(algo) == Events.DILUTION_EVENT
