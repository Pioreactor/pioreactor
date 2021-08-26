# -*- coding: utf-8 -*-
# gpio helpers

from enum import Enum
from contextlib import contextmanager
from pioreactor.utils import local_intermittent_storage


class GPIO_states(Enum):
    GPIO_AVAILABLE = b"1"
    GPIO_UNAVAILABLE = b"0"


def set_gpio_availability(pin: int, is_in_use: GPIO_states):
    with local_intermittent_storage("gpio_in_use") as cache:
        cache[str(pin)] = is_in_use.value


def is_gpio_available(pin: int) -> bool:
    with local_intermittent_storage("gpio_in_use") as cache:
        return (
            cache.get(str(pin), GPIO_states.GPIO_AVAILABLE) == GPIO_states.GPIO_AVAILABLE
        )


@contextmanager
def temporarily_set_gpio_unavailable(pin: int):
    """

    Examples
    ---------

    > with temporarily_set_gpio_unavailable(16):
    >    # do stuff with pin 16
    >
    """
    try:
        set_gpio_availability(pin, GPIO_states.GPIO_UNAVAILABLE)
        yield
    finally:
        set_gpio_availability(pin, GPIO_states.GPIO_AVAILABLE)
