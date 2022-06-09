# -*- coding: utf-8 -*-
# gpio helpers
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from pioreactor.types import GpioPin
from pioreactor.utils import local_intermittent_storage

GPIO_IN_USE = "in_use"


def set_gpio_availability(pin: GpioPin, available: bool) -> None:
    pin_key = str(pin)
    with local_intermittent_storage("gpio_in_use") as cache:
        if not available:
            cache[pin_key] = GPIO_IN_USE
        else:
            if pin_key in cache:
                del cache[pin_key]


def is_gpio_available(pin: GpioPin) -> bool:
    with local_intermittent_storage("gpio_in_use") as cache:
        return cache.get(str(pin)) == GPIO_IN_USE


@contextmanager
def temporarily_set_gpio_unavailable(pin: GpioPin) -> Iterator[None]:
    """

    Examples
    ---------

    > with temporarily_set_gpio_unavailable(16):
    >    # do stuff with pin 16
    >
    """
    try:
        set_gpio_availability(pin, False)
        yield
    finally:
        set_gpio_availability(pin, True)
