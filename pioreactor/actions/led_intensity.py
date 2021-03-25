# -*- coding: utf-8 -*-
import logging
import json
import click
from pioreactor.pubsub import publish_multiple, subscribe, QOS
from pioreactor.whoami import (
    UNIVERSAL_EXPERIMENT,
    get_unit_name,
    get_latest_experiment_name,
)


logger = logging.getLogger("led_intensity")
CHANNELS = ["A", "B", "C", "D"]


def get_current_state_from_broker(unit):
    # this ignores the status of "power on"
    msg = subscribe(
        f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/leds/intensity", timeout=0.5
    )
    if msg:
        return json.loads(msg.payload)
    else:
        return {c: 0 for c in CHANNELS}


def led_intensity(
    channel, intensity, source_of_event=None, unit=None, experiment=None, verbose=True
):
    """
    State is also updated in

    pioreactor/<unit>/<experiment>/leds/<channel>/intensity intensity

    and

    pioreactor/<unit>/<experiment>/leds/intensity {'A': intensityA, 'B': 0, ...}

    1. The way state is handled in the second topic is tech debt.

    """
    try:
        from DAC43608 import DAC43608
    except NotImplementedError:
        print("DAC43608 not available; using MockDAC43608")
        from pioreactor.utils.mock import MockDAC43608 as DAC43608

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
        state = get_current_state_from_broker(unit)
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
                    f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/leds/{channel}/intensity",
                    intensity,
                    QOS.AT_MOST_ONCE,
                    True,
                ),
                (
                    f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/leds/intensity",
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
@click.option("--channel", type=click.Choice(CHANNELS, case_sensitive=False))
@click.option(
    "--intensity", help="value between 0 and 100", type=click.FloatRange(0, 100)
)
@click.option(
    "--source-of-event",
    default="app",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_led_intensity(channel, intensity, source_of_event):
    """
    Modify the intensity of an LED
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return led_intensity(channel, intensity, source_of_event, unit, experiment)
