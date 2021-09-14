# -*- coding: utf-8 -*-
# testing_led_control

import time, json

from pioreactor.background_jobs.led_control import LEDController
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor import pubsub


unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.5)


def test_silent():
    ld = LEDController("silent", unit=unit, experiment=experiment)
    pause()
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.01, "timestamp": "2010-01-01 12:00:00"}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        '{"od_filtered": 1.0}',
    )
    pause()
    r = pubsub.subscribe(
        f"pioreactor/{unit}/{experiment}/led_control/led_automation", timeout=1
    )
    assert r.payload.decode() == "silent"
    ld.set_state(ld.DISCONNECTED)
