# -*- coding: utf-8 -*-
import logging
import json
from pioreactor.pubsub import publish, subscribe
from DAC43608 import DAC43608


logger = logging.getLogger("led_intensity")


def get_current_state_from_broker(unit, experiment):
    msg = subscribe(f"pioreactor/{unit}/{experiment}/leds/intensity", timeout=0.5)
    if msg:
        return json.loads(msg.payload)
    else:
        return {"A": 0, "B": 0, "C": 0, "D": 0}


def led_intensity(channel, intensity=0.0, unit=None, experiment=None):
    """
    State is also updated in

    pioreactor/<unit>/<experiment>/leds/<channel>/intensity intensity

    and

    pioreactor/<unit>/<experiment>/leds/intensity {'A': intensityA, 'B': 0, ...}

    1. The way state is handled in the second topic is tech debt.

    """
    assert 0 <= intensity <= 100
    assert channel in ["A", "B", "C", "D"]
    try:
        dac = DAC43608()
        dac.power_to(getattr(dac, channel), intensity / 100)

        publish(
            f"pioreactor/{unit}/{experiment}/leds/{channel}/intensity",
            intensity,
            retain=True,
        )
        state = get_current_state_from_broker(unit, experiment)
        state[channel] = intensity
        publish(
            f"pioreactor/{unit}/{experiment}/leds/intensity",
            json.dumps(state),
            retain=True,
        )
        return True
    except Exception as e:
        logger.debug(e, exc_info=True)
        logger.error(e)
        return False
