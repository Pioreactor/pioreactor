# -*- coding: utf-8 -*-
from __future__ import annotations

import time

from msgspec.json import encode

from pioreactor import pubsub
from pioreactor import structs
from pioreactor.actions.led_intensity import LED_UNLOCKED
from pioreactor.actions.led_intensity import lock_leds_temporarily
from pioreactor.automations.led.base import LEDAutomationJob
from pioreactor.background_jobs.led_control import LEDController
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.timing import current_utc_time
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def pause() -> None:
    # to avoid race conditions when updating state
    time.sleep(0.5)


def test_silent() -> None:
    experiment = "test_silent"
    with LEDController("silent", duration=60, unit=unit, experiment=experiment) as ld:
        pause()
        pause()
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.01, timestamp=current_utc_time())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=1.0, timestamp=current_utc_time())),
        )
        pause()
        pause()
        r = pubsub.subscribe(
            f"pioreactor/{unit}/{experiment}/led_control/automation_name", timeout=1
        )
        assert r is not None
        assert r.payload.decode() == "silent"
        assert ld.automation_job.latest_od == 1.0
        assert ld.automation_job.latest_growth_rate == 0.01


def test_changing_automation_over_mqtt() -> None:
    experiment = "test_changing_automation_over_mqtt"
    original_duration = 60
    with LEDController(
        "silent", duration=original_duration, unit=unit, experiment=experiment
    ) as ld:
        assert ld.automation_name == "silent"
        assert ld.automation_job.duration == original_duration
        pause()
        pause()
        r = pubsub.subscribe(
            f"pioreactor/{unit}/{experiment}/led_control/automation_name", timeout=1
        )
        assert r is not None
        assert r.payload.decode() == "silent"
        pause()
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/led_control/automation/set",
            encode(
                structs.LEDAutomation(
                    automation_name="silent",
                    automation_type="led",
                    args={"duration": 20},
                )
            ),
        )
        pause()
        pause()
        pause()
        pause()
        pause()
        pause()
        pause()
        assert ld.automation_name == "silent"
        assert ld.automation_job.duration == 20


def test_we_respect_any_locks_on_leds_we_want_to_modify() -> None:
    """
    This test works locally, but not in github CI
    """
    experiment = "test_we_respect_any_locks_on_leds_we_want_to_modify"
    with local_intermittent_storage("led_locks") as cache:
        cache["A"] = LED_UNLOCKED
        cache["B"] = LED_UNLOCKED
        cache["C"] = LED_UNLOCKED
        cache["D"] = LED_UNLOCKED

    with LEDAutomationJob(duration=1, unit=unit, experiment=experiment) as ld:
        pause()
        pause()

        assert ld.set_led_intensity("B", 1)

        # someone else locks channel B
        with lock_leds_temporarily(["B"]):
            assert not ld.set_led_intensity("B", 2)

        assert ld.set_led_intensity("B", 3)
