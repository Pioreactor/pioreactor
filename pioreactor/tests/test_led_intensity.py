# -*- coding: utf-8 -*-
# test_led_intensity
import pytest
from pioreactor.actions.led_intensity import (
    lock_leds_temporarily,
    led_intensity,
    LedChannel,
)
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.utils import local_intermittent_storage


def test_lock_will_prevent_led_from_updating() -> None:

    channel: LedChannel = "A"

    unit = get_unit_name()
    exp = get_latest_experiment_name()

    assert led_intensity(channels=channel, intensities=20, unit=unit, experiment=exp)

    with lock_leds_temporarily([channel]):
        assert not led_intensity(
            channels=channel, intensities=10, unit=unit, experiment=exp
        )

    with local_intermittent_storage("leds") as cache:
        assert float(cache[channel]) == 20


def test_lock_will_prevent_led_from_updating_single_channel_but_not_others_passed_in() -> None:

    unit = get_unit_name()
    exp = get_latest_experiment_name()

    assert led_intensity(
        channels=["A", "B"], intensities=[20, 20], unit=unit, experiment=exp
    )

    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == 20
        assert float(cache["A"]) == 20

    with lock_leds_temporarily(["A"]):
        assert not led_intensity(
            channels=["A", "B"], intensities=[10, 10], unit=unit, experiment=exp
        )

    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == 10
        assert float(cache["A"]) == 20


def test_error_is_thrown_if_lengths_are_wrong() -> None:
    unit = get_unit_name()
    exp = get_latest_experiment_name()

    with pytest.raises(ValueError):
        led_intensity(channels=["A", "B"], intensities=[20], unit=unit, experiment=exp)

    with pytest.raises(ValueError):
        led_intensity(channels=["A", "B"], intensities=20, unit=unit, experiment=exp)

    assert led_intensity(channels=["A"], intensities=20, unit=unit, experiment=exp)


def test_local_cache_is_updated() -> None:

    channel: LedChannel = "B"

    unit = get_unit_name()
    exp = get_latest_experiment_name()

    assert led_intensity(channels=channel, intensities=20, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == 20
