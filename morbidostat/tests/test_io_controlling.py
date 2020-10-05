# -*- coding: utf-8 -*-

import pytest

from morbidostat.long_running.io_controlling import io_controlling, ControlAlgorithm
from morbidostat.long_running import events
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
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", "0.01"),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", "1.0"),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", "0.02"),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", "1.1"),
    )

    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)
    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)

    io = io_controlling(mode="silent", volume=None, duration=60, verbose=True)
    assert isinstance(next(io), events.NoEvent)
    assert isinstance(next(io), events.NoEvent)


def test_turbidostat_algorithm(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.98),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 1.0),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 1.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.99),
    )

    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)
    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)

    target_od = 1.0
    algo = io_controlling(mode="turbidostat", target_od=target_od, duration=60, volume=0.25, verbose=True)

    assert isinstance(next(algo), events.NoEvent)
    assert isinstance(next(algo), events.DilutionEvent)
    assert isinstance(next(algo), events.DilutionEvent)
    assert isinstance(next(algo), events.NoEvent)


def test_pid_turbidostat_algorithm(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.20),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.8),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.88),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.95),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.97),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.99),
    )

    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)
    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)

    target_od = 1.0
    algo = io_controlling(mode="pid_turbidostat", target_od=target_od, volume=0.25, duration=60, verbose=True)

    assert isinstance(next(algo), events.NoEvent)
    assert isinstance(next(algo), events.DilutionEvent)
    assert isinstance(next(algo), events.DilutionEvent)
    assert isinstance(next(algo), events.DilutionEvent)
    assert isinstance(next(algo), events.DilutionEvent)


def test_morbidostat_algorithm(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.95),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.99),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 1.05),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 1.03),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 1.04),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.01),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.99),
    )

    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)
    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)

    target_od = 1.0
    algo = io_controlling(mode="morbidostat", target_od=target_od, duration=60, volume=0.25, verbose=True)

    assert isinstance(next(algo), events.NoEvent)
    assert isinstance(next(algo), events.DilutionEvent)
    assert isinstance(next(algo), events.AltMediaEvent)
    assert isinstance(next(algo), events.DilutionEvent)
    assert isinstance(next(algo), events.AltMediaEvent)
    assert isinstance(next(algo), events.DilutionEvent)


def test_pid_morbidostat_algorithm(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.08),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.95),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.07),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.95),
        MockMQTTMsg("morbidostat/_testing/_experiment/growth_rate", 0.065),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_filtered/135", 0.95),
    )

    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)
    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)

    target_growth_rate = 0.09
    algo = io_controlling(mode="pid_morbidostat", target_od=1.0, target_growth_rate=target_growth_rate, duration=60, verbose=True)

    event = next(algo)
    assert isinstance(event, events.AltMediaEvent)
    assert isinstance(next(algo), events.AltMediaEvent)
    assert isinstance(next(algo), events.AltMediaEvent)


def test_execute_io_action():
    ca = ControlAlgorithm(verbose=True, unit="_testing", experiment="_testing")
    ca.execute_io_action(media_ml=0.65, alt_media_ml=0.15, waste_ml=0.80)
