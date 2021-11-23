# -*- coding: utf-8 -*-
# testing_led_control

import time, json

from pioreactor.background_jobs.led_control import LEDController
from pioreactor.automations.led.base import LEDAutomation
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor import pubsub
from pioreactor.actions.led_intensity import lock_leds_temporarily
from pioreactor.utils import local_intermittent_storage

unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause() -> None:
    # to avoid race conditions when updating state
    time.sleep(0.5)


def test_silent() -> None:
    with LEDController("silent", duration=60, unit=unit, experiment=experiment):
        pause()
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
        pause()
        r = pubsub.subscribe(
            f"pioreactor/{unit}/{experiment}/led_control/led_automation_name", timeout=1
        )
        assert r.payload.decode() == "silent"


def test_changing_automation_over_mqtt() -> None:
    with LEDController("silent", duration=60, unit=unit, experiment=experiment) as ld:

        pause()
        pause()
        r = pubsub.subscribe(
            f"pioreactor/{unit}/{experiment}/led_control/led_automation_name", timeout=1
        )
        assert r.payload.decode() == "silent"
        pause()
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/led_control/led_automation/set",
            '{"automation_name": "silent", "duration": "20"}',
        )
        pause()
        pause()
        pause()
        pause()
        pause()
        assert ld.led_automation_name == "silent"
        assert ld.led_automation["duration"] == "20"


def test_we_respect_any_locks_on_leds_we_want_to_modify() -> None:
    with local_intermittent_storage("led_locks") as cache:
        cache["A"] = b"0"
        cache["B"] = b"0"
        cache["C"] = b"0"
        cache["D"] = b"0"

    with LEDAutomation(duration=1, unit=unit, experiment=experiment) as ld:
        pause()
        pause()
        assert ld.set_led_intensity("B", 1)

        # someone else locks channel B
        with lock_leds_temporarily(["B"]):
            assert not ld.set_led_intensity("B", 2)

        assert ld.set_led_intensity("B", 3)
