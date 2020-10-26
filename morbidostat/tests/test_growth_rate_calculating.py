# -*- coding: utf-8 -*-
import pytest
import json

from morbidostat.background_jobs.growth_rate_calculating import GrowthRateCalculator
from morbidostat.pubsub import subscribe, publish
from morbidostat.whoami import unit, experiment


def test_subscribing(monkeypatch):

    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}')
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}')
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}')
    publish(f"morbidostat/{unit}/{experiment}/io_event", '{"volume_change": "1.5", "event": "add_media"}')
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 1.778586260567034, "90/A": 1.20944389172032837}')
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 1.778586260567034, "90/A": 1.20944389172032837}')

    calc = GrowthRateCalculator(unit, experiment)
    calc.run()
    calc.run()
    calc.run()
    calc.run()


def test_same_angles(monkeypatch):
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90": 0.1}'
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.808586260567034, "135/B": 0.21944389172032837, "90": 0.2}'
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.808586260567034, "135/B": 0.21944389172032837, "90": 0.2}'
    )

    calc = GrowthRateCalculator(unit, experiment)
    calc.run()
    calc.run()


def test_mis_shapen_data(monkeypatch):
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135": 0.778586260567034, "90": 0.1}')
    publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135": 0.808586260567034}')

    calc = GrowthRateCalculator(unit, experiment)

    with pytest.raises(AssertionError):
        calc.run()
        calc.run()


def test_restart(monkeypatch):
    publish(f"morbidostat/{unit}/{experiment}/growth_rate", None, retain=True)

    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90": 0.1}'
    )
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

    calc1 = GrowthRateCalculator(unit, experiment)
    calc1.run()
    calc1.run()

    calc2 = GrowthRateCalculator(unit, experiment)
    calc2.run()


def test_skip_180(monkeypatch):
    publish(f"morbidostat/{unit}/{experiment}/growth_rate", None, retain=True)
    publish(
        f"morbidostat/{unit}/{experiment}/od_normalization_factors", json.dumps({"135/A": 1, "90/A": 1, "180/A": 1}), retain=True
    )

    calc = GrowthRateCalculator(unit, experiment)
    stream = calc.run()

    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched",
        '{"180/A": 0.778586260567034, "135/A": 0.20944389172032837, "90/A": 0.1}',
    )
    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched",
        '{"180/A": 0.778586260567034, "135/A": 0.20944389172032837, "90/A": 0.1}',
    )
    assert next(stream)[0] != "180/A"
    assert next(stream)[0] != "180/A"

    publish(
        f"morbidostat/{unit}/{experiment}/od_raw_batched",
        '{"180/A": 0.778586260567034, "135/A": 0.20944389172032837, "90/A": 0.1}',
    )
    assert next(stream)[0] != "180/A"
    assert next(stream)[0] != "180/A"
