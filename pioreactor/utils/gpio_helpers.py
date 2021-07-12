# -*- coding: utf-8 -*-
# gpio helpers

from pioreactor.utils import local_intermittent_storage

GPIO_AVAILABLE = b"1"
GPIO_UNAVAILABLE = b"0"


def set_gpio_availability(pin, is_in_use):
    assert is_in_use in [GPIO_AVAILABLE, GPIO_UNAVAILABLE]
    with local_intermittent_storage("gpio_in_use") as cache:
        cache[str(pin)] = is_in_use


def is_gpio_available(pin):
    with local_intermittent_storage("gpio_in_use") as cache:
        return cache.get(str(pin), GPIO_AVAILABLE) == GPIO_AVAILABLE
