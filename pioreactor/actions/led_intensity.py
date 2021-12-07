# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import click
from typing import Tuple, Dict, Optional, Union, Literal, Iterator
from contextlib import contextmanager

from paho.mqtt.client import Client  # type: ignore

from pioreactor.pubsub import create_client, QOS
from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor.logging import create_logger
from pioreactor.utils.timing import current_utc_time
from pioreactor.utils import local_intermittent_storage


LED_Channel = Literal["A", "B", "C", "D"]
ALL_LED_CHANNELS: list[LED_Channel] = ["A", "B", "C", "D"]


LED_LOCKED = b"1"
LED_UNLOCKED = b"0"


@contextmanager
def change_leds_intensities_temporarily(
    channels: list[LED_Channel], new_intensities: list[float], **kwargs
) -> Iterator[None]:
    """
    Change the LED referenced in `channels` to some intensity `new_intensities`
    inside the context block. Once the context block has left, change
    back to the old intensities (even if the intensities were changed inside the block.)

    """
    try:
        with local_intermittent_storage("leds") as cache:
            old_state = {c: float(cache.get(c, 0)) for c in channels}

        led_intensity(channels, new_intensities, **kwargs)

        yield
    finally:
        led_intensity(list(old_state.keys()), list(old_state.values()), **kwargs)


@contextmanager
def lock_leds_temporarily(channels: list[LED_Channel]) -> Iterator[None]:
    try:
        with local_intermittent_storage("led_locks") as cache:
            for c in channels:
                cache[c] = LED_LOCKED
        yield
    finally:
        with local_intermittent_storage("led_locks") as cache:
            for c in channels:
                cache[c] = LED_UNLOCKED


def is_locked(channel: LED_Channel) -> bool:
    with local_intermittent_storage("led_locks") as cache:
        return cache.get(channel, LED_UNLOCKED) == LED_LOCKED


def _update_current_state(
    channels: list[LED_Channel],
    intensities: list[float],
) -> Tuple[Dict[LED_Channel, float], Dict[LED_Channel, float]]:
    """
    Previously this used MQTT, but network latency could really cause trouble.
    Eventually I should try to modify the UI to not even need this `state` variable,
    """

    with local_intermittent_storage("leds") as led_cache:
        old_state = {
            channel: float(led_cache.get(channel, 0)) for channel in ALL_LED_CHANNELS
        }

        # update cache
        for channel, intensity in zip(channels, intensities):
            led_cache[channel] = str(intensity)

        new_state = {
            channel: float(led_cache.get(channel, 0)) for channel in ALL_LED_CHANNELS
        }

        return new_state, old_state


def _list(x: Union[list, float, str]) -> list:
    if isinstance(x, list):
        return x
    else:
        return [x]


def led_intensity(
    channels: Union[LED_Channel, list[LED_Channel]],
    intensities: Union[float, list[float]],
    source_of_event: Optional[str] = None,
    verbose: bool = True,
    pubsub_client: Optional[Client] = None,
    unit: str = None,
    experiment: str = None,
) -> bool:
    """

    Parameters
    ------------
    channel: an LED channel or list
    intensity: float or list
        a value between 0 and 100 to set the LED channel to.
    verbose: bool
        if True, log the change, and send event to led_event table & mqtt. This is FALSE
        in od_reading job, so as to not create spam.
    pubsub_client:
        provide a MQTT paho client to use for publishing.

    Returns
    --------
    bool representing if the all LED channels intensity were successfully changed


    State is also updated in

    pioreactor/<unit>/<experiment>/led/<channel>/intensity   <intensity>

    and

    pioreactor/<unit>/<experiment>/leds/intensity    {'A': intensityA, 'B': intensityB, ...}

    """
    logger = create_logger("led_intensity", experiment=experiment, unit=unit)
    updated_successfully = True
    if not is_testing_env():
        from DAC43608 import DAC43608
    else:
        logger.debug("DAC43608 not available; using MockDAC43608")
        from pioreactor.utils.mock import MockDAC43608 as DAC43608  # type: ignore

    if pubsub_client is None:
        pubsub_client = create_client()

    channels, intensities = _list(channels), _list(intensities)

    if len(channels) != len(intensities):
        raise RuntimeError("channels must be the same length as intensities")

    # any locked channels?
    for channel in channels:
        if is_locked(channel):
            updated_successfully = False
            logger.warning(
                f"Unable to update channel {channel} due to a lock on it. Please try again."
            )

    # remove locked channels:
    try:
        channels, intensities = zip(  # type: ignore
            *[(c, i) for c, i in zip(channels, intensities) if not is_locked(c)]
        )
    except ValueError:
        # if the only channel being updated is locked, the resulting error is a ValueError: not enough values to unpack (expected 2, got 0)
        return updated_successfully

    for channel, intensity in zip(channels, intensities):
        try:
            assert (
                0.0 <= intensity <= 100.0
            ), "intensity should be between 0 and 100, inclusive"
            assert (
                channel in ALL_LED_CHANNELS
            ), f"saw incorrect channel {channel}, not in {ALL_LED_CHANNELS}"
            intensity = float(intensity)

            dac = DAC43608()
            dac.power_up(getattr(dac, channel))
            dac.set_intensity_to(getattr(dac, channel), intensity / 100.0)

            if intensity == 0:
                # setting to 0 doesn't fully remove the current, there is some residual current. We turn off
                # the channel to guarantee no output.
                dac.power_down(getattr(dac, channel))

            pubsub_client.publish(
                f"pioreactor/{unit}/{experiment}/led/{channel}/intensity",
                intensity,
                qos=QOS.AT_MOST_ONCE,
                retain=True,
            )

        except ValueError as e:
            logger.debug(e, exc_info=True)
            logger.error(
                "Unable to find I²C for LED driver. Is the Pioreactor HAT attached to the Raspberry Pi? Is I²C enabled on the Raspberry Pi?"
            )
            updated_successfully = False
            return updated_successfully

    new_state, old_state = _update_current_state(channels, intensities)

    pubsub_client.publish(
        f"pioreactor/{unit}/{experiment}/leds/intensity",
        json.dumps(new_state),
        qos=QOS.AT_MOST_ONCE,
        retain=True,
    )

    if verbose:
        for channel, intensity in zip(channels, intensities):
            event = {
                "channel": channel,
                "intensity": intensity,
                "source_of_event": source_of_event,
                "timestamp": current_utc_time(),
            }

            pubsub_client.publish(
                f"pioreactor/{unit}/{experiment}/led_events",
                json.dumps(event),
                qos=QOS.AT_MOST_ONCE,
                retain=False,
            )

            logger.info(
                f"Updated LED {channel} from {old_state[channel]:0.3g}% to {new_state[channel]:0.3g}%."
            )

    return updated_successfully


@click.command(name="led_intensity")
@click.option(
    "--channel",
    type=click.Choice(ALL_LED_CHANNELS, case_sensitive=False),
    multiple=True,
    required=True,
)
@click.option(
    "--intensity",
    help="value between 0 and 100",
    type=click.FloatRange(0, 100),
    required=True,
)
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="whom is calling this function (for logging purposes)",
)
@click.option("--no-log", is_flag=True, help="Add to log")
def click_led_intensity(channel, intensity, source_of_event, no_log):
    """
    Modify the intensity of LED channel(s)
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    status = led_intensity(
        channels=list(channel),
        intensities=[intensity] * len(channel),
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
        verbose=not no_log,
    )
    return status
