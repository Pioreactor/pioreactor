# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from contextlib import contextmanager
from contextlib import nullcontext
from typing import Any
from typing import Iterator

import click
from msgspec.json import encode

from pioreactor import structs
from pioreactor.exc import HardwareNotFoundError
from pioreactor.logging import create_logger
from pioreactor.pubsub import Client
from pioreactor.pubsub import create_client
from pioreactor.pubsub import QOS
from pioreactor.types import LedChannel
from pioreactor.types import LedIntensityValue
from pioreactor.utils import JobManager
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_active
from pioreactor.whoami import is_testing_env

ALL_LED_CHANNELS: list[LedChannel] = ["A", "B", "C", "D"]
LEDsToIntensityMapping = dict[LedChannel, LedIntensityValue]


@contextmanager
def change_leds_intensities_temporarily(
    desired_state: LEDsToIntensityMapping,
    **kwargs: Any,
) -> Iterator[None]:
    """
    Change the LED referenced in `channels` to some intensity `new_intensities`
    inside the context block. Once the context block has left, change
    back to the old intensities (even if the intensities were changed inside the block.)

    """
    old_state = {}
    try:
        with local_intermittent_storage("leds") as cache:
            old_state = {c: cache.get(c, 0.0) for c in desired_state.keys()}

        if not led_intensity(desired_state, **kwargs):
            raise ValueError("Unable to update LED.")

        yield
    finally:
        if not led_intensity(old_state, **kwargs):
            raise ValueError("Unable to update LED.")


@contextmanager
def lock_leds_temporarily(channels: list[LedChannel]) -> Iterator[None]:
    try:
        with local_intermittent_storage("led_locks") as cache:
            for c in channels:
                cache[c] = os.getpid()
        yield
    finally:
        with local_intermittent_storage("led_locks") as cache:
            for c in channels:
                cache.pop(c)


def is_led_channel_locked(channel: LedChannel) -> bool:
    with local_intermittent_storage("led_locks") as cache:
        return cache.get(channel) is not None


def _update_current_state(
    state: LEDsToIntensityMapping,
) -> tuple[LEDsToIntensityMapping, LEDsToIntensityMapping]:
    """
    TODO: Eventually I should try to modify the UI to not even need this `state` variable,
    """

    with local_intermittent_storage("leds") as led_cache:
        # rehydrate old cache
        old_state: LEDsToIntensityMapping = {
            channel: led_cache.get(str(channel), 0.0) for channel in ALL_LED_CHANNELS
        }

        # update cache
        for channel, intensity in state.items():
            led_cache[channel] = intensity

        new_state: LEDsToIntensityMapping = {
            channel: led_cache.get(str(channel), 0.0) for channel in ALL_LED_CHANNELS
        }

        return new_state, old_state


def led_intensity(
    desired_state: LEDsToIntensityMapping,
    unit: str | None = None,
    experiment: str | None = None,
    verbose: bool = True,
    source_of_event: str | None = None,
    pubsub_client: Client | None = None,
) -> bool:
    """
    Change the intensity of the LED channels A,B,C, or D to an value between 0 and 100.

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
    State is updated in MQTT and the temporary cache `leds`:

        pioreactor/<unit>/<experiment>/leds/intensity    {'A': intensityA, 'B': intensityB, ...}

    """
    unit = unit or get_unit_name()
    experiment = experiment or get_assigned_experiment_name(unit)

    if not is_active(unit):
        return False

    logger = create_logger("led_intensity", experiment=experiment, unit=unit, pub_client=pubsub_client)
    updated_successfully = True

    if not is_testing_env():
        from pioreactor.utils.dacs import DAC
    else:
        from pioreactor.utils.mock import Mock_DAC as DAC  # type: ignore

    if pubsub_client is None:
        mqtt_publishing = create_client(client_id=f"led_intensity-{unit}-{experiment}")
        mqtt_publish = mqtt_publishing.publish
    else:
        mqtt_publishing = nullcontext()
        mqtt_publish = pubsub_client.publish

    with mqtt_publishing:
        # any locked channels?
        for channel in list(desired_state.keys()):
            if is_led_channel_locked(channel):
                logger.debug(
                    f"Unable to update channel {channel} due to a software lock on it. Please try again."
                )
                desired_state = {k: v for k, v in desired_state.items() if k != channel}

                updated_successfully = False

        for channel, intensity in desired_state.items():
            try:
                assert (
                    channel in ALL_LED_CHANNELS
                ), f"Saw incorrect channel {channel}, not in {ALL_LED_CHANNELS}"
                assert (
                    0.0 <= intensity <= 100.0
                ), f"Channel {channel} intensity should be between 0 and 100, inclusive"

                dac = DAC()
                dac.set_intensity_to(getattr(dac, channel), intensity)
            except (ValueError, HardwareNotFoundError) as e:
                logger.debug(e, exc_info=True)
                logger.error(
                    "Unable to find i2c for LED driver. Is the Pioreactor HAT attached to the Raspberry Pi? Is the firmware loaded?"
                )
                updated_successfully = False
                return updated_successfully
            except AssertionError as e:
                logger.error(e)
                updated_successfully = False
                return updated_successfully

        new_state, old_state = _update_current_state(desired_state)

        mqtt_publish(
            f"pioreactor/{unit}/{experiment}/leds/intensity",
            encode(new_state),
            qos=QOS.AT_MOST_ONCE,
            retain=True,
        )

        # this is a hack to deal with there _not_ being a process that controls LEDs when run from the command line with `pio run` (tip: maybe that changes...)
        # If `pio run led_intensity` is run, it's given a unique pid. This pid won't exist in the DB, so
        # we register it with the job manager. Later, when we run `pio kill x`, we run `pio run led_intensity --A 0..` in LEDKill(), which trips the second condition, so we don't
        # end up re-adding it.
        # if something like OD reading starts led_intesity, it's pid exists, so we don't register it.
        with JobManager() as jm:
            if jm.does_pid_exist(os.getpid()) or new_state == {"A": 0, "B": 0, "C": 0, "D": 0}:
                # part of a larger job, or turning off LEDs as part of LEDKill()
                pass
            else:
                jm.register_and_set_running(
                    unit,
                    experiment,
                    "led_intensity",
                    os.environ.get("JOB_SOURCE", "user"),
                    os.getpid(),
                    "",
                    False,
                )

        if verbose:
            timestamp_of_change = current_utc_datetime()

            for channel, intensity in desired_state.items():
                event = structs.LEDChangeEvent(
                    channel=channel,
                    intensity=intensity,
                    source_of_event=source_of_event,
                    timestamp=timestamp_of_change,
                )

                mqtt_publish(
                    f"pioreactor/{unit}/{experiment}/led_change_events",
                    encode(event),
                    qos=QOS.AT_MOST_ONCE,
                    retain=False,
                )

                logger.info(
                    f"Updated LED {channel} from {old_state[channel]:0.3g}% to {new_state[channel]:0.3g}%."
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
@click.option("--no-log", is_flag=True, help="skip logging")
def click_led_intensity(
    a: LedIntensityValue | None = None,
    b: LedIntensityValue | None = None,
    c: LedIntensityValue | None = None,
    d: LedIntensityValue | None = None,
    source_of_event: str | None = None,
    no_log: bool = False,
) -> bool:
    """
    Modify the intensity of LED channel(s)
    """
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    state: LEDsToIntensityMapping = {}
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
