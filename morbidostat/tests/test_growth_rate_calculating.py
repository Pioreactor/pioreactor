# -*- coding: utf-8 -*-
import pytest
import json
import time

from morbidostat.background_jobs.growth_rate_calculating import GrowthRateCalculator, MedianFirstN
from morbidostat.pubsub import subscribe, publish
from morbidostat.whoami import unit, experiment


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.5)


def setup_module(module):
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}',
        retain=True,
    )


def test_subscribing(monkeypatch):

    calc = GrowthRateCalculator(unit, experiment)
    publish(f"morbidostat/{unit}/{experiment}/growth_rate", 1.0)
    pause()
    assert calc.initial_growth_rate == 1.0

    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}')
    pause()

    assert calc.ekf is not None

    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}')
    publish(f"morbidostat/{unit}/{experiment}/io_event", '{"volume_change": "1.5", "event": "add_media"}')
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 1.778586260567034, "90/A": 1.20944389172032837}')
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 1.778586260567034, "90/A": 1.20944389172032837}')
    pause()

    assert calc.state_ is not None


def test_same_angles(monkeypatch):
    calc = GrowthRateCalculator(unit, experiment)
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90": 0.1}'
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.808586260567034, "135/B": 0.21944389172032837, "90": 0.2}'
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.808586260567034, "135/B": 0.21944389172032837, "90": 0.2}'
    )


def test_mis_shapen_data(monkeypatch):
    calc = GrowthRateCalculator(unit, experiment)

    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135": 0.778586260567034, "90": 0.1}')
    pause()

    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135": 0.808586260567034}')
    pause()


def test_restart():
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90": 0.1}',
        retain=True,
    )
    publish(f"morbidostat/{unit}/{experiment}/growth_rate", None, retain=True)
    pause()
    calc1 = GrowthRateCalculator(unit, experiment)

    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 1.808586260567034, "135/B": 1.21944389172032837, "90": 1.2}'
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 2.808586260567034, "135/B": 2.21944389172032837, "90": 2.2}'
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 3.808586260567034, "135/B": 3.21944389172032837, "90": 3.2}'
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 4.808586260567034, "135/B": 4.21944389172032837, "90": 4.2}'
    )
    pause()

    assert calc1.state_[-1] != 0

    calc2 = GrowthRateCalculator(unit, experiment)
    pause()
    assert calc2.initial_growth_rate != 0


def test_skip_180():
    publish(f"morbidostat/{unit}/{experiment}/growth_rate", None, retain=True)
    publish(
        f"morbidostat/{unit}/{experiment}/od_normalization_factors", json.dumps({"135/A": 1, "90/A": 1, "180/A": 1}), retain=True
    )

    calc = GrowthRateCalculator(unit, experiment)

    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched",
        '{"180/A": 0.778586260567034, "135/A": 0.20944389172032837, "90/A": 0.1}',
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched",
        '{"180/A": 0.778586260567034, "135/A": 0.20944389172032837, "90/A": 0.1}',
    )
    pause()

    assert "180/A" not in calc.angles


def test_MedianFirstN():

    m = MedianFirstN(N=3)
    m.update({"d": 1, "t": 2})
    m.update({"d": 1, "t": 3})
    m.update({"d": 1, "t": 4})
    assert m.reduced_data == {"d": 1, "t": 3}


def test_MedianFirstN_from_dict():

    m = MedianFirstN.from_dict({"d": 1, "t": 2})
    assert m["d"] == 1
    assert m["t"] == 2


def test_VarianceOfResidualsFirstN():
    import numpy as np

    publish(f"morbidostat/{unit}/{experiment}/growth_rate", None, retain=True)
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", None, retain=True)

    def to_thread():
        for i in range(500):
            obs = {"135/A": 0.1 * np.random.randn(), "90/A": 1 * np.random.randn()}
            publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", json.dumps(obs))

    import threading

    t = threading.Thread(target=to_thread)
    t.start()
    calc = GrowthRateCalculator(unit, experiment)

    t.join()
