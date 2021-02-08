# -*- coding: utf-8 -*-
import logging
import json
import click
from pioreactor.pubsub import publish, subscribe, QOS
from pioreactor.whoami import get_latest_experiment_name, get_unit_name


logger = logging.getLogger("led_intensity")
CHANNELS = ["A", "B", "C", "D"]


def get_current_state_from_broker(unit, experiment):
    # TODO: It's possible to also get this information from the DAC device. Not
    # sure what is better
    # this also ignores the status of "power on"
    msg = subscribe(f"pioreactor/{unit}/{experiment}/leds/intensity", timeout=0.5)
    if msg:
        return json.loads(msg.payload)
    else:
        return {c: 0 for c in CHANNELS}


def led_intensity(
    channel, intensity=0.0, source_of_event=None, unit=None, experiment=None
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
    except Exception as e:
        logger.debug(e, exc_info=True)
        logger.error(e)
        return False
    else:
        state = get_current_state_from_broker(unit, experiment)
        old_intensity = state[channel]
        state[channel] = intensity

        logger.info(f"Updated LED {channel} from {old_intensity} to {intensity}.")
        publish(
            f"pioreactor/{unit}/{experiment}/leds/{channel}/intensity",
            intensity,
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/leds/intensity",
            json.dumps(state),
            retain=True,
        )

        publish(
            f"pioreactor/{unit}/{experiment}/led_events",
            json.dumps(
                {
                    "channel": channel,
                    "intensity": intensity,
                    "event": "change_intensity",
                    "source_of_event": source_of_event,
                }
            ),
            qos=QOS.EXACTLY_ONCE,
        )

        return True


@click.command(name="led_intensity")
@click.option("--channel", type=click.Choice(CHANNELS, case_sensitive=False))
@click.option("--intensity", help="value between 0 and 100", type=click.IntRange(0, 100))
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
