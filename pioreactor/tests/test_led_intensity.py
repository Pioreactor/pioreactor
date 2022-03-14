# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.actions.led_intensity import change_leds_intensities_temporarily
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.actions.led_intensity import LedChannel
from pioreactor.actions.led_intensity import lock_leds_temporarily
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_unit_name


def test_lock_will_prevent_led_from_updating() -> None:

    channel: LedChannel = "A"

    unit = get_unit_name()
    exp = "test_lock_will_prevent_led_from_updating"

    assert led_intensity({"A": 20}, unit=unit, experiment=exp)

    with lock_leds_temporarily([channel]):
        assert not led_intensity({"A": 10}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache[channel]) == 20


def test_lock_will_prevent_led_from_updating_single_channel_but_not_others_passed_in() -> None:

    unit = get_unit_name()
    exp = (
        "test_lock_will_prevent_led_from_updating_single_channel_but_not_others_passed_in"
    )

    assert led_intensity({"A": 20, "B": 20}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == 20
        assert float(cache["A"]) == 20

    with lock_leds_temporarily(["A"]):
        assert not led_intensity({"A": 10, "B": 10}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == 10
        assert float(cache["A"]) == 20


def test_change_leds_intensities_temporarily() -> None:

    unit = get_unit_name()
    exp = "test_change_leds_intensities_temporarily"

    led_intensity({"A": 20, "B": 20}, unit=unit, experiment=exp)

    with change_leds_intensities_temporarily({"A": 10}, unit=unit, experiment=exp):
        with local_intermittent_storage("leds") as cache:
            assert float(cache["A"]) == 10
            assert float(cache["B"]) == 20

    with local_intermittent_storage("leds") as cache:
        assert float(cache["A"]) == 20
        assert float(cache["B"]) == 20

    with change_leds_intensities_temporarily(
        {"A": 10, "C": 10, "D": 0}, unit=unit, experiment=exp
    ):
        with local_intermittent_storage("leds") as cache:
            assert float(cache["A"]) == 10
            assert float(cache["B"]) == 20
            assert float(cache["C"]) == 10
            assert float(cache["D"]) == 0

    with local_intermittent_storage("leds") as cache:
        assert float(cache["A"]) == 20
        assert float(cache["C"]) == 0
        assert float(cache["D"]) == 0


def test_local_cache_is_updated() -> None:

    channel: LedChannel = "B"

    unit = get_unit_name()
    exp = "test_local_cache_is_updated"

    assert led_intensity({channel: 20}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache[channel]) == 20
