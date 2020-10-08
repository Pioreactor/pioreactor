# -*- coding: utf-8 -*-
import pytest

from morbidostat.background_jobs.growth_rate_calculating import growth_rate_calculating
from paho.mqtt import subscribe, publish


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


def test_subscribing(monkeypatch):

    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/_experiment/od_raw_batched", '{"135": 0.778586260567034, "90": 0.20944389172032837}'),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_raw_batched", '{"135": 0.778586260567034, "90": 0.20944389172032837}'),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_raw_batched", '{"135": 0.778586260567034, "90": 0.20944389172032837}'),
        MockMQTTMsg("morbidostat/_testing/_experiment/io_event", '{"volume_change": "1.5", "event": "add_media"}'),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_raw_batched", '{"135": 1.778586260567034, "90": 1.20944389172032837}'),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_raw_batched", '{"135": 1.778586260567034, "90": 1.20944389172032837}'),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc = growth_rate_calculating()
    next(calc)
    next(calc)
    next(calc)
    next(calc)


def test_same_angles(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"135A": 0.778586260567034, "135B": 0.20944389172032837, "90": 0.1}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"135A": 0.808586260567034, "135B": 0.21944389172032837, "90": 0.2}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"135A": 0.808586260567034, "135B": 0.21944389172032837, "90": 0.2}',
        ),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc = growth_rate_calculating()
    next(calc)
    next(calc)


def test_mis_shapen_data(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg("morbidostat/_testing/_experiment/od_raw_batched", '{"135": 0.778586260567034, "90": 0.1}'),
        MockMQTTMsg("morbidostat/_testing/_experiment/od_raw_batched", '{"135": 0.808586260567034}'),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc = growth_rate_calculating()

    with pytest.raises(AssertionError):
        next(calc)
        next(calc)


def test_restart(monkeypatch):
    publish.single("morbidostat/_testing/_experiment/growth_rate", None, retain=True)

    mock_broker = MockMsgBroker(
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"135A": 0.778586260567034, "135B": 0.20944389172032837, "90": 0.1}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"135A": 1.808586260567034, "135B": 1.21944389172032837, "90": 1.2}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"135A": 2.808586260567034, "135B": 2.21944389172032837, "90": 2.2}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"135A": 3.808586260567034, "135B": 3.21944389172032837, "90": 3.2}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"135A": 4.808586260567034, "135B": 4.21944389172032837, "90": 4.2}',
        ),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc1 = growth_rate_calculating(verbose=True)
    next(calc1)
    next(calc1)

    calc2 = growth_rate_calculating(verbose=True)
    next(calc2)


def test_skip_180(monkeypatch):
    publish.single("morbidostat/_testing/_experiment/growth_rate", None, retain=True)

    mock_broker = MockMsgBroker(
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"180": 0.778586260567034, "135B": 0.20944389172032837, "90": 0.1}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"180": 1.808586260567034, "135B": 1.21944389172032837, "90": 1.2}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"180": 2.808586260567034, "135B": 2.21944389172032837, "90": 2.2}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"180": 3.808586260567034, "135B": 3.21944389172032837, "90": 3.2}',
        ),
        MockMQTTMsg(
            "morbidostat/_testing/_experiment/od_raw_batched",
            '{"180": 4.808586260567034, "135B": 4.21944389172032837, "90": 4.2}',
        ),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc1 = growth_rate_calculating(verbose=True)
    next(calc1)
    next(calc1)
