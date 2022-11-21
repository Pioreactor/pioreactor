# -*- coding: utf-8 -*-
from __future__ import annotations

import time

from msgspec.json import encode

from pioreactor import pubsub
from pioreactor import structs
from pioreactor.actions.led_intensity import lock_leds_temporarily
from pioreactor.automations.led.base import LEDAutomationJob
from pioreactor.background_jobs.led_control import LEDController
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def pause(n=1) -> None:
    # to avoid race conditions when updating state
    time.sleep(n * 0.5)


def test_silent() -> None:
    experiment = "test_silent"
    with LEDController("silent", duration=60, unit=unit, experiment=experiment) as ld:
        pause()
        pause()
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.01, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=1.0, timestamp=current_utc_datetime())),
        )
        pause()
        pause()
        r = pubsub.subscribe(
            f"pioreactor/{unit}/{experiment}/led_control/automation_name", timeout=1
        )
        assert r is not None
        assert r.payload.decode() == "silent"
        assert ld.automation_job.latest_normalized_od == 1.0
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
    experiment = "test_we_respect_any_locks_on_leds_we_want_to_modify"
    with local_intermittent_storage("led_locks") as cache:
        for c in cache.iterkeys():
            del cache[c]

    with LEDAutomationJob(duration=1, unit=unit, experiment=experiment) as ld:
        pause()
        pause()

        assert ld.set_led_intensity("B", 1)

        # someone else locks channel B
        with lock_leds_temporarily(["B"]):
            assert not ld.set_led_intensity("B", 2)

        assert ld.set_led_intensity("B", 3)


def test_light_dark_cycle_starts_on() -> None:
    experiment = "test_light_dark_cycle_starts_on"
    unit = get_unit_name()
    with LEDController(
        "light_dark_cycle",
        duration=60,
        light_intensity=50,
        light_duration_hours=16,
        dark_duration_hours=8,
        unit=unit,
        experiment=experiment,
    ) as lc:
        pause(6)

        assert lc.automation_job.light_active
        with local_intermittent_storage("leds") as c:
            assert c["D"] == 50
            assert c["C"] == 50


def test_light_dark_cycle_turns_off_after_N_cycles() -> None:
    experiment = "test_light_dark_cycle_turns_off_after_N_cycles"
    unit = get_unit_name()
    with LEDController(
        "light_dark_cycle",
        duration=0.01,
        light_intensity=50,
        light_duration_hours=16,
        dark_duration_hours=8,
        unit=unit,
        experiment=experiment,
    ) as lc:
        while lc.automation_job.hours_online < 17:
            pass

        assert not lc.automation_job.light_active
        with local_intermittent_storage("leds") as c:
            assert c["D"] == 0.0
            assert c["C"] == 0.0


def test_dark_duration_hour_to_zero() -> None:
    experiment = "test_dark_duration_hour_to_zero"
    unit = get_unit_name()
    with LEDController(
        "light_dark_cycle",
        duration=0.01,
        light_intensity=50,
        light_duration_hours=16,
        dark_duration_hours=8,
        unit=unit,
        experiment=experiment,
    ) as lc:
        while lc.automation_job.hours_online < 17:
            pass

        assert not lc.automation_job.light_active

        lc.automation_job.set_dark_duration_hours(0)

        assert lc.automation_job.light_active

        with local_intermittent_storage("leds") as c:
            assert c["D"] == 50.0
            assert c["C"] == 50.0


def test_light_duration_hour_to_zero() -> None:
    experiment = "test_light_duration_hour_to_zero"
    unit = get_unit_name()
    with LEDController(
        "light_dark_cycle",
        duration=0.01,
        light_intensity=50,
        light_duration_hours=16,
        dark_duration_hours=8,
        unit=unit,
        experiment=experiment,
    ) as lc:

        pause(6)
        assert lc.automation_job.light_active

        lc.automation_job.set_light_duration_hours(0)

        assert not lc.automation_job.light_active


def test_add_dark_duration_hours() -> None:
    experiment = "test_add_dark_duration_hours"
    unit = get_unit_name()
    with LEDController(
        "light_dark_cycle",
        duration=0.01,
        light_intensity=50,
        light_duration_hours=16,
        dark_duration_hours=8,
        unit=unit,
        experiment=experiment,
    ) as lc:
        while lc.automation_job.hours_online < 17:
            pass

        assert not lc.automation_job.light_active

        lc.automation_job.set_dark_duration_hours(10)

        assert not lc.automation_job.light_active

        with local_intermittent_storage("leds") as c:
            assert c["D"] == 0.0
            assert c["C"] == 0.0


def test_remove_dark_duration_hours() -> None:
    experiment = "test_remove_dark_duration_hours"
    unit = get_unit_name()
    with LEDController(
        "light_dark_cycle",
        duration=0.01,
        light_intensity=50,
        light_duration_hours=16,
        dark_duration_hours=8,
        unit=unit,
        experiment=experiment,
    ) as lc:
        while lc.automation_job.hours_online < 20:
            pass

        assert not lc.automation_job.light_active

        lc.automation_job.set_dark_duration_hours(3)

        assert lc.automation_job.light_active

        with local_intermittent_storage("leds") as c:
            assert c["D"] == 50.0
            assert c["C"] == 50.0
