# -*- coding: utf-8 -*-
import pytest

from morbidostat.background_jobs.growth_rate_calculating import GrowthRateCalculator
from paho.mqtt import subscribe, publish
from morbidostat.whoami import unit, experiment


class MockMQTTMsg:
    def __init__(self, topic, payload):
        self.payload = payload
        self.topic = topic


class MockMsgBroker:
    # TODO: remove this.
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

    def callback(self, func, topics, hostname="localhost", **kwargs):
        self._add_callback(func, topics)
        return


def test_subscribing(monkeypatch):

    mock_broker = MockMsgBroker(
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}'
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}'
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}'
        ),
        MockMQTTMsg(f"morbidostat/{unit}/{experiment}/io_event", '{"volume_change": "1.5", "event": "add_media"}'),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 1.778586260567034, "90/A": 1.20944389172032837}'
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 1.778586260567034, "90/A": 1.20944389172032837}'
        ),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc = GrowthRateCalculator(unit, experiment)
    calc.run()
    calc.run()
    calc.run()
    calc.run()


def test_same_angles(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90": 0.1}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"135/A": 0.808586260567034, "135/B": 0.21944389172032837, "90": 0.2}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"135/A": 0.808586260567034, "135/B": 0.21944389172032837, "90": 0.2}',
        ),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc = GrowthRateCalculator(unit, experiment)
    calc.run()
    calc.run()


def test_mis_shapen_data(monkeypatch):
    mock_broker = MockMsgBroker(
        MockMQTTMsg(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135": 0.778586260567034, "90": 0.1}'),
        MockMQTTMsg(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135": 0.808586260567034}'),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc = GrowthRateCalculator(unit, experiment)

    with pytest.raises(AssertionError):
        calc.run()
        calc.run()


def test_restart(monkeypatch):
    publish.single(f"morbidostat/{unit}/{experiment}/growth_rate", None, retain=True)

    mock_broker = MockMsgBroker(
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90": 0.1}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"135/A": 1.808586260567034, "135/B": 1.21944389172032837, "90": 1.2}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"135/A": 2.808586260567034, "135/B": 2.21944389172032837, "90": 2.2}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"135/A": 3.808586260567034, "135/B": 3.21944389172032837, "90": 3.2}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"135/A": 4.808586260567034, "135/B": 4.21944389172032837, "90": 4.2}',
        ),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc1 = GrowthRateCalculator(unit, experiment)
    calc1.run()
    calc1.run()

    calc2 = GrowthRateCalculator(unit, experiment)
    calc2.run()


def test_skip_180(monkeypatch):
    publish.single(f"morbidostat/{unit}/{experiment}/growth_rate", None, retain=True)

    mock_broker = MockMsgBroker(
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"180/A": 0.778586260567034, "135/A": 0.20944389172032837, "90/A": 0.1}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"180/A": 1.808586260567034, "135/A": 1.21944389172032837, "90/A": 1.2}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"180/A": 2.808586260567034, "135/A": 2.21944389172032837, "90/A": 2.2}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"180/A": 3.808586260567034, "135/A": 3.21944389172032837, "90/A": 3.2}',
        ),
        MockMQTTMsg(
            f"morbidostat/{unit}/{experiment}/od_raw_batched",
            '{"180/A": 4.808586260567034, "135/A": 4.21944389172032837, "90/A": 4.2}',
        ),
    )

    monkeypatch.setattr(subscribe, "simple", mock_broker.subscribe)
    monkeypatch.setattr(subscribe, "callback", mock_broker.callback)

    calc = GrowthRateCalculator(unit, experiment)
    calc.run()
    calc.run()
