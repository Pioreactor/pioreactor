# -*- coding: utf-8 -*-
import json
import time
import numpy as np

from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.pubsub import publish
from pioreactor.whoami import get_unit_name, get_latest_experiment_name

unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.5)


def test_subscribing(monkeypatch):
    publish(f"pioreactor/{unit}/{experiment}/od_normalization/median", None, retain=True)
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance", None, retain=True
    )
    publish(f"pioreactor/{unit}/{experiment}/growth_rate", None, retain=True)

    publish(f"pioreactor/{unit}/{experiment}/growth_rate", 1.0, retain=True)
    calc = GrowthRateCalculator(unit=unit, experiment=experiment)
    pause()
    assert calc.initial_growth_rate == 1.0

    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}',
    )
    pause()

    assert calc.ekf is not None

    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "90/A": 0.20944389172032837}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/io_event",
        '{"volume_change": "1.5", "event": "add_media"}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 1.778586260567034, "90/A": 1.20944389172032837}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 1.778586260567034, "90/A": 1.20944389172032837}',
    )
    pause()

    assert calc.state_ is not None


def test_same_angles(monkeypatch):
    publish(f"pioreactor/{unit}/{experiment}/od_normalization/median", None, retain=True)
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance", None, retain=True
    )
    publish(f"pioreactor/{unit}/{experiment}/growth_rate", None, retain=True)

    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90/A": 0.1}',
        retain=True,
    )

    GrowthRateCalculator(unit=unit, experiment=experiment)
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90/A": 0.1}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.808586260567034, "135/B": 0.21944389172032837, "90/A": 0.2}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.808586260567034, "135/B": 0.21944389172032837, "90/A": 0.2}',
    )


def test_mis_shapen_data(monkeypatch):
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "90/A": 0.1}',
        retain=True,
    )

    GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "90/A": 0.1}',
    )
    pause()

    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.808586260567034}'
    )
    pause()


def test_restart():
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90/A": 0.1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/median",
        '{"135/A": 0.778586260567034, "135/B": 0.20944389172032837, "90/A": 0.1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        '{"135/A": 1, "135/B": 1, "90/A": 1}',
        retain=True,
    )
    publish(f"pioreactor/{unit}/{experiment}/growth_rate", None, retain=True)
    pause()
    calc1 = GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 1.808586260567034, "135/B": 1.21944389172032837, "90/A": 1.2}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 2.808586260567034, "135/B": 2.21944389172032837, "90/A": 2.2}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 3.808586260567034, "135/B": 3.21944389172032837, "90/A": 3.2}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 4.808586260567034, "135/B": 4.21944389172032837, "90/A": 4.2}',
    )
    pause()

    assert calc1.state_[-1] != 0

    calc2 = GrowthRateCalculator(unit=unit, experiment=experiment)
    pause()
    assert calc2.initial_growth_rate != 0


def test_skip_180():
    publish(f"pioreactor/{unit}/{experiment}/growth_rate", None, retain=True)
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"180/A": 0.778586260567034, "135/A": 0.20944389172032837, "90/A": 0.1}',
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"180/A": 0.778586260567034, "135/A": 0.20944389172032837, "90/A": 0.1}',
    )
    pause()

    assert "180/A" not in calc.angles


def test_scaling_works():

    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/median",
        json.dumps({"135/A": 0.5, "90/A": 0.8}),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        json.dumps({"135/A": 1e-6, "90/A": 1e-4}),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched",
        '{"135/A": 0.5, "90/A": 0.8}',
        retain=True,
    )
    publish(f"pioreactor/{unit}/{experiment}/growth_rate", "", retain=True)

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.51, "90/A": 0.82}'
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.51, "90/A": 0.83}'
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_raw_batched", '{"135/A": 0.51, "90/A": 0.84}'
    )
    pause()
    assert calc.od_normalization_factors == {"90/A": 0.8, "135/A": 0.5}
    assert (
        (
            calc.ekf.observation_noise_covariance
            - 30 * np.array([[1e-4 / 0.8 ** 2, 0], [0, 1e-6 / 0.5 ** 2]])
        )
        < 1e-7
    ).all()
