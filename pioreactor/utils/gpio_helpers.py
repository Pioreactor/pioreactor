# -*- coding: utf-8 -*-
# gpio helpers

from enum import Enum
from contextlib import contextmanager
from typing import Iterator
from pioreactor.utils import local_intermittent_storage
from pioreactor.types import GPIO_Pin


class GPIO_states(Enum):
    GPIO_AVAILABLE = "1"
    GPIO_UNAVAILABLE = "0"


def set_gpio_availability(pin: GPIO_Pin, is_in_use: GPIO_states) -> None:
    with local_intermittent_storage("gpio_in_use") as cache:
        cache[str(pin)] = is_in_use.value


def is_gpio_available(pin: GPIO_Pin) -> bool:
    with local_intermittent_storage("gpio_in_use") as cache:
        return (
            cache.get(str(pin), GPIO_states.GPIO_AVAILABLE) == GPIO_states.GPIO_AVAILABLE
        )


@contextmanager
def temporarily_set_gpio_unavailable(pin: GPIO_Pin) -> Iterator[None]:
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
