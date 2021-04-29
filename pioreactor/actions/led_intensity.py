# -*- coding: utf-8 -*-
import json
import click
from pioreactor.pubsub import publish_multiple, subscribe, QOS
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.logging import create_logger


CHANNELS = ["A", "B", "C", "D"]


def get_current_state_from_broker(unit, experiment):
    # this ignores the status of "power on"
    # TODO: this is kinda bad, overall. To keep state in MQTT, and if
    #       we timeout, we basically reset state completely.
    msg = subscribe(f"pioreactor/{unit}/{experiment}/leds/intensity", timeout=2)
    if msg:
        return json.loads(msg.payload)
    else:
        return {c: 0 for c in CHANNELS}


def led_intensity(
    channel,
    intensity,
    source_of_event=None,
    unit=None,
    experiment=None,
    verbose=True,
    mock=False,
):
    """
    State is also updated in

    pioreactor/<unit>/<experiment>/leds/<channel>/intensity intensity

    and

    pioreactor/<unit>/<experiment>/leds/intensity {'A': intensityA, 'B': 0, ...}

    1. The way state is handled in the second topic is tech debt.

    """
    logger = create_logger("led_intensity")
    try:
        from DAC43608 import DAC43608
    except NotImplementedError:
        logger.debug("DAC43608 not available; using MockDAC43608")
        from pioreactor.utils.mock import MockDAC43608 as DAC43608

    if mock:
        from pioreactor.utils.mock import MockDAC43608 as DAC43608  # noqa: F811

    try:
        assert 0 <= intensity <= 100
        assert channel in CHANNELS
        dac = DAC43608()
        dac.power_up(getattr(dac, channel))
        dac.set_intensity_to(getattr(dac, channel), intensity / 100)
    except ValueError as e:
        logger.debug(e, exc_info=True)
        logger.error(
            "Is the Pioreactor HAT attached to the RaspberryPi? Unable to find I²C for LED driver."
        )
        return False
    else:
        state = get_current_state_from_broker(unit, experiment)
        old_intensity = state[channel]
        state[channel] = intensity

        if verbose:
            logger.info(f"Updated LED {channel} from {old_intensity} to {intensity}.")

        event = {
            "channel": channel,
            "intensity": intensity,
            "event": "change_intensity",
            "source_of_event": source_of_event,
        }

        # we publish some state to UNIVERSAL_EXPERIMENT because
        # LED intensity can stay on over multiple experiments,
        # and is more of a "state" than a measurement.
        publish_multiple(
            [
                (
                    f"pioreactor/{unit}/{experiment}/leds/{channel}/intensity",
                    intensity,
                    QOS.AT_MOST_ONCE,
                    True,
                ),
                (
                    f"pioreactor/{unit}/{experiment}/leds/intensity",
                    json.dumps(state),
                    QOS.AT_MOST_ONCE,
                    True,
                ),
                (
                    f"pioreactor/{unit}/{experiment}/led_events",
                    json.dumps(event),
                    QOS.EXACTLY_ONCE,
                    False,
                ),
            ]
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
def click_led_intensity(channel, intensity, source_of_event):
    """
    Modify the intensity of LED channel(s)
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    status = True
    for channel_ in channel:
        status &= led_intensity(channel_, intensity, source_of_event, unit, experiment)
    return status
