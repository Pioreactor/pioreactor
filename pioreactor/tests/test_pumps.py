# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import threading
import time

import pytest

from pioreactor.actions.add_alt_media import add_alt_media
from pioreactor.actions.add_media import add_media
from pioreactor.actions.remove_waste import remove_waste
from pioreactor.pubsub import publish
from pioreactor.utils import local_persistant_storage
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name

unit = get_unit_name()
exp = get_latest_experiment_name()


def pause(n=1):
    time.sleep(n)


def setup_function():
    with local_persistant_storage("pump_calibration") as cache:
        cache["media_ml_calibration"] = json.dumps(
            {"duration_": 1.0, "bias_": 0, "dc": 60, "hz": 100, "timestamp": "2010-01-01"}
        )
        cache["alt_media_ml_calibration"] = json.dumps(
            {"duration_": 1.0, "bias_": 0, "dc": 60, "hz": 100, "timestamp": "2010-01-01"}
        )
        cache["waste_ml_calibration"] = json.dumps(
            {"duration_": 1.0, "bias_": 0, "dc": 60, "hz": 100, "timestamp": "2010-01-01"}
        )


def test_pump_io() -> None:
    ml = 0.1
    assert ml == add_media(ml=ml, unit=unit, experiment=exp)
    assert ml == add_alt_media(ml=ml, unit=unit, experiment=exp)
    assert ml == remove_waste(ml=ml, unit=unit, experiment=exp)

    ml = 1.0
    assert ml == add_media(duration=ml, unit=unit, experiment=exp)
    assert ml == add_alt_media(duration=ml, unit=unit, experiment=exp)
    assert ml == remove_waste(duration=ml, unit=unit, experiment=exp)


def test_pump_io_doesnt_allow_negative() -> None:
    with pytest.raises(AssertionError):
        add_media(ml=-1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        add_alt_media(ml=-1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        remove_waste(ml=-1, unit=unit, experiment=exp)

    with pytest.raises(AssertionError):
        add_media(duration=-1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        add_alt_media(duration=-1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        remove_waste(duration=-1, unit=unit, experiment=exp)


def test_pump_io_cant_set_both_duration_and_ml() -> None:
    with pytest.raises(AssertionError):
        add_media(ml=1, duration=1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        add_alt_media(ml=1, duration=1, unit=unit, experiment=exp)
    with pytest.raises(AssertionError):
        remove_waste(ml=1, duration=1, unit=unit, experiment=exp)


def test_pump_will_disconnect_via_mqtt() -> None:
    class ThreadWithReturnValue(threading.Thread):
        def __init__(self, *init_args, **init_kwargs):
            threading.Thread.__init__(self, *init_args, **init_kwargs)
            self._return = None

        def run(self):
            self._return = self._target(*self._args, **self._kwargs)

        def join(self):
            threading.Thread.join(self)
            return self._return

    expected_ml = 20
    t = ThreadWithReturnValue(
        target=add_media, args=(unit, exp, expected_ml), daemon=True
    )
    t.start()

    pause()
    pause()
    publish(f"pioreactor/{unit}/{exp}/media_pump/$state/set", "disconnected")
    pause()

    resulting_ml = t.join()

    assert resulting_ml < expected_ml
