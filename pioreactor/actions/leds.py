# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger("led_intensity")


def led_intensity(channel=None, intensity=0.0):
    assert 0 <= intensity <= 100
    assert channel in ["A", "B", "C", "D"]
    try:
        return True
    except Exception as e:
        logger.debug(e, exc_info=True)
        logger.error(e)
        return False
