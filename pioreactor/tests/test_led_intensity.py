# -*- coding: utf-8 -*-
# test_led_intensity
from pioreactor.actions.led_intensity import (
    lock_leds_temporarily,
    LED_Channel,
    led_intensity,
)
from pioreactor.utils import local_intermittent_storage


def test_lock_will_prevent_led_from_updating():

    channel = LED_Channel("A")

    assert led_intensity(channels=channel, intensities=20)

    with lock_leds_temporarily([channel]):
        assert not led_intensity(channels=channel, intensities=10)


def test_local_cache_is_updated():

    channel = LED_Channel("B")
    assert led_intensity(channels=channel, intensities=20)

    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == 20
