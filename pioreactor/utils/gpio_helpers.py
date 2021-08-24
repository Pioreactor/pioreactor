# -*- coding: utf-8 -*-
# gpio helpers

from pioreactor.utils import local_intermittent_storage
from contextlib import contextmanager


GPIO_AVAILABLE = b"1"
GPIO_UNAVAILABLE = b"0"


def set_gpio_availability(pin, is_in_use):
    assert is_in_use in [GPIO_AVAILABLE, GPIO_UNAVAILABLE]
    with local_intermittent_storage("gpio_in_use") as cache:
        cache[str(pin)] = is_in_use


def is_gpio_available(pin):
    with local_intermittent_storage("gpio_in_use") as cache:
        return cache.get(str(pin), GPIO_AVAILABLE) == GPIO_AVAILABLE


@contextmanager
def temporarily_set_gpio_unavailable(pin):
    """

    Examples
    ---------

    > with temporarily_set_gpio_unavailable(16):
    >    # do stuff with pin 16
    >
    """
    try:
        set_gpio_availability(pin, GPIO_UNAVAILABLE)
        yield
    finally:
        set_gpio_availability(pin, GPIO_AVAILABLE)
