# -*- coding: utf-8 -*-
import json
import click

from pioreactor.pubsub import create_client, QOS
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.logging import create_logger
from pioreactor.utils.timing import current_utc_time
from pioreactor.utils import local_intermittent_storage

CHANNELS = ["A", "B", "C", "D"]


def update_current_state(channel, intensity):
    """
    this ignores the status of "power on"

    This use to use MQTT, but network latency could really cause trouble.
    Eventually I should try to modify the UI to not even need this `state` variable,
    """

    with local_intermittent_storage("leds") as led_cache:
        old_state = {channel: float(led_cache.get(channel, 0)) for channel in CHANNELS}

        # update cache
        led_cache[channel] = str(intensity)

        new_state = {channel: float(led_cache.get(channel, 0)) for channel in CHANNELS}

        return new_state, old_state


def led_intensity(
    channel,
    intensity,
    source_of_event=None,
    unit=None,
    experiment=None,
    verbose=True,
    mock=False,
    pubsub_client=None,
):
    """
    State is also updated in

    pioreactor/<unit>/<experiment>/leds/<channel>/intensity intensity

    and

    pioreactor/<unit>/<experiment>/leds/intensity {'A': intensityA, 'B': intensityB, ...}

    1. The way state is handled in the second topic is tech debt.

    """
    logger = create_logger("led_intensity", experiment=experiment)
    try:
        from DAC43608 import DAC43608
    except NotImplementedError:
        logger.debug("DAC43608 not available; using MockDAC43608")
        from pioreactor.utils.mock import MockDAC43608 as DAC43608

    if mock:
        from pioreactor.utils.mock import MockDAC43608 as DAC43608  # noqa: F811

    if pubsub_client is None:
        pubsub_client = create_client()

    try:
        assert 0 <= intensity <= 100
        assert channel in CHANNELS, f"saw incorrect channel {channel}"
        dac = DAC43608()
        dac.power_up(getattr(dac, channel))
        dac.set_intensity_to(getattr(dac, channel), intensity / 100)

        if intensity == 0:
            # setting to 0 doesn't fully remove the current, there is some residual current. We turn off
            # the channel to guarantee no output.
            dac.power_down(getattr(dac, channel))

    except ValueError as e:
        logger.debug(e, exc_info=True)
        logger.error(
            "Is the Pioreactor HAT attached to the Raspberry Pi? Unable to find I²C for LED driver."
        )
        return False
    else:
        new_state, old_state = update_current_state(channel, intensity)

        if verbose:
            logger.info(
                f"Updated LED {channel} from {old_state[channel]:g}% to {new_state[channel]:g}%."
            )

        event = {
            "channel": channel,
            "intensity": intensity,
            "event": "change_intensity",
            "source_of_event": source_of_event,
            "timestamp": current_utc_time(),
        }

        pubsub_client.publish(
            f"pioreactor/{unit}/{experiment}/leds/{channel}/intensity",
            intensity,
            qos=QOS.AT_MOST_ONCE,
            retain=True,
        )
        pubsub_client.publish(
            f"pioreactor/{unit}/{experiment}/leds/intensity",
            json.dumps(new_state),
            qos=QOS.AT_MOST_ONCE,
            retain=True,
        )
        pubsub_client.publish(
            f"pioreactor/{unit}/{experiment}/led_events",
            json.dumps(event),
            qos=QOS.AT_MOST_ONCE,
            retain=False,
        )

        return True


@click.command(name="led_intensity")
@click.option(
    "--channel",
    type=click.Choice(CHANNELS, case_sensitive=False),
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
    help="whom is calling this function (for logging)",
)
@click.option("--no-log", is_flag=True, help="Add to log")
def click_led_intensity(channel, intensity, source_of_event, no_log):
    """
    Modify the intensity of LED channel(s)
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    status = True
    for channel_ in channel:
        status &= led_intensity(
            channel_, intensity, source_of_event, unit, experiment, verbose=not no_log
        )
    return status
