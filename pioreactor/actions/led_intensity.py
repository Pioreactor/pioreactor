# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from typing import Iterator
from typing import Optional

import click
from msgspec.json import encode

from pioreactor import structs
from pioreactor.logging import create_logger
from pioreactor.pubsub import Client
from pioreactor.pubsub import create_client
from pioreactor.pubsub import QOS
from pioreactor.types import LedChannel
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env

ALL_LED_CHANNELS: list[LedChannel] = ["A", "B", "C", "D"]


LED_LOCKED = b"1"
LED_UNLOCKED = b"0"


def _list(x) -> list:
    if isinstance(x, list):
        return x
    elif isinstance(x, tuple):
        return list(x)
    else:
        return [x]


@contextmanager
def change_leds_intensities_temporarily(
    desired_state: dict[LedChannel, float],
    **kwargs: Any,
) -> Iterator[None]:
    """
    Change the LED referenced in `channels` to some intensity `new_intensities`
    inside the context block. Once the context block has left, change
    back to the old intensities (even if the intensities were changed inside the block.)

    """
    try:
        with local_intermittent_storage("leds") as cache:
            old_state = {c: float(cache.get(c, 0.0)) for c in desired_state.keys()}

        led_intensity(desired_state, **kwargs)

        yield
    finally:
        led_intensity(old_state, **kwargs)


@contextmanager
def lock_leds_temporarily(channels: list[LedChannel]) -> Iterator[None]:
    try:
        with local_intermittent_storage("led_locks") as cache:
            for c in channels:
                cache[c] = LED_LOCKED
        yield
    finally:
        with local_intermittent_storage("led_locks") as cache:
            for c in channels:
                cache[c] = LED_UNLOCKED


def is_led_channel_locked(channel: LedChannel) -> bool:
    with local_intermittent_storage("led_locks") as cache:
        return cache.get(channel, LED_UNLOCKED) == LED_LOCKED


def _update_current_state(
    new_state,
) -> tuple[structs.LEDsIntensity, structs.LEDsIntensity]:
    """
    Previously this used MQTT, but network latency could really cause trouble.
    Eventually I should try to modify the UI to not even need this `state` variable,
    """

    with local_intermittent_storage("leds") as led_cache:
        # rehydrate old cache
        old_state = structs.LEDsIntensity(
            **{channel.decode(): float(led_cache.get(channel, 0.0)) for channel in led_cache.keys()}
        )

        # update cache
        for channel, intensity in new_state.items():
            led_cache[channel] = str(intensity)

        new_state = structs.LEDsIntensity(
            **{channel.decode(): float(led_cache.get(channel, 0.0)) for channel in led_cache.keys()}
        )

        return new_state, old_state


def led_intensity(
    desired_state: dict[LedChannel, float],
    unit: str,
    experiment: str,
    verbose: bool = True,
    source_of_event: Optional[str] = None,
    pubsub_client: Optional[Client] = None,
) -> bool:
    """
    Change the intensity of the LED channels A,B,C, or D.

    Parameters
    ------------
    desired_state: dict
        what you want the desired LED state to be. Leave keys out if you do wish to update that channel.
    unit: str
    experiment: str
    verbose: bool
        if True, log the change, and send event to led_event table & mqtt. This is FALSE
        in od_reading job, so as to not create spam.
    source_of_event: str
        A human readable string of who is calling this function
    pubsub_client:
        provide a MQTT paho client to use for publishing.


    Returns
    --------
    bool representing if the all LED channels intensity were successfully changed


    Notes
    -------
    State is updated in MQTT:

        pioreactor/<unit>/<experiment>/leds/intensity    {'A': intensityA, 'B': intensityB, ...}

    """
    assert experiment is not None, "experiment must be set"
    assert unit is not None, "unit must be set"
    logger = create_logger("led_intensity", experiment=experiment, unit=unit)
    updated_successfully = True
    if not is_testing_env():
        from DAC43608 import DAC43608
    else:
        logger.debug("DAC43608 not available; using MockDAC43608")
        from pioreactor.utils.mock import MockDAC43608 as DAC43608  # type: ignore

    if pubsub_client is None:
        pubsub_client = create_client()

    # any locked channels?
    for channel in list(desired_state.keys()):
        if is_led_channel_locked(channel):
            updated_successfully = False
            logger.warning(
                f"Unable to update channel {channel} due to a lock on it. Please try again."
            )
            del desired_state[channel]

    for channel, intensity in desired_state.items():
        try:
            assert 0.0 <= intensity <= 100.0, "intensity should be between 0 and 100, inclusive"
            assert (
                channel in ALL_LED_CHANNELS
            ), f"saw incorrect channel {channel}, not in {ALL_LED_CHANNELS}"

            dac = DAC43608()
            dac.power_up(getattr(dac, channel))
            dac.set_intensity_to(getattr(dac, channel), intensity / 100.0)

            if intensity == 0.0:
                # setting to 0 doesn't fully remove the current, there is some residual current. We turn off
                # the channel to guarantee no output.
                dac.power_down(getattr(dac, channel))

        except ValueError as e:
            logger.debug(e, exc_info=True)
            logger.error(
                "Unable to find I²C for LED driver. Is the Pioreactor HAT attached to the Raspberry Pi? Is I²C enabled on the Raspberry Pi?"
            )
            updated_successfully = False
            return updated_successfully

    new_state, old_state = _update_current_state(desired_state)

    pubsub_client.publish(
        f"pioreactor/{unit}/{experiment}/leds/intensity",
        encode(new_state),
        qos=QOS.AT_MOST_ONCE,
        retain=True,
    )

    if verbose:
        for channel, intensity in desired_state.items():
            event = structs.LEDChangeEvent(
                channel=channel,
                intensity=intensity,
                source_of_event=source_of_event,
                timestamp=current_utc_timestamp(),
            )

            pubsub_client.publish(
                f"pioreactor/{unit}/{experiment}/led_change_events",
                encode(event),
                qos=QOS.AT_MOST_ONCE,
                retain=False,
            )

            logger.info(
                f"Updated LED {channel} from {getattr(old_state, channel):0.3g}% to {getattr(new_state, channel):0.3g}%."
            )

    return updated_successfully


@click.command(name="led_intensity")
@click.option(
    "--A",
    help="value between 0 and 100",
    type=click.FloatRange(0, 100),
)
@click.option(
    "--B",
    help="value between 0 and 100",
    type=click.FloatRange(0, 100),
)
@click.option(
    "--C",
    help="value between 0 and 100",
    type=click.FloatRange(0, 100),
)
@click.option(
    "--D",
    help="value between 0 and 100",
    type=click.FloatRange(0, 100),
)
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="whom is calling this function (for logging purposes)",
)
@click.option("--no-log", is_flag=True, help="Add to log")
def click_led_intensity(
    a: Optional[float] = None,
    b: Optional[float] = None,
    c: Optional[float] = None,
    d: Optional[float] = None,
    source_of_event: str = None,
    no_log: bool = False,
) -> bool:
    """
    Modify the intensity of LED channel(s)
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    state: dict[LedChannel, float] = {}
    if a is not None:
        state["A"] = a
    if b is not None:
        state["B"] = b
    if c is not None:
        state["C"] = c
    if d is not None:
        state["D"] = d

    status = led_intensity(
        state,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
        verbose=not no_log,
    )
    return status
