# -*- coding: utf-8 -*-
# testing_led_control

import time

from pioreactor.background_jobs.led_control import LEDController
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor import pubsub


unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.5)


def test_silent():
    LEDController("silent", unit=unit, experiment=experiment)
    pause()
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate", "0.01"
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered", "1.0"
    )
    pause()
    r = pubsub.subscribe(
        f"pioreactor/{unit}/{experiment}/led_control/led_automation", timeout=1
    )
    assert r.payload.decode() == "silent"


def test_track_od():

    con = LEDController("track_od", unit=unit, experiment=experiment, max_od=2.0)
    pause()
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate", "0.01"
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered", "1.0"
    )
    pause()
    pause()
    r = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/leds/B/intensity", timeout=1)
    assert float(r.payload.decode()) == 10

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate", "0.01"
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered", "2.0"
    )
    pause()
    con.led_automation_job.run()
    pause()
    r = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/leds/B/intensity", timeout=1)
    assert float(r.payload.decode()) == 100
