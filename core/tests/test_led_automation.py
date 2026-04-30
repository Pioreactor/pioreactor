# -*- coding: utf-8 -*-
import time
from datetime import timedelta
from typing import Callable

import pytest
from msgspec.json import encode
from pioreactor import pubsub
from pioreactor import structs
from pioreactor.actions.led_intensity import lock_leds_temporarily
from pioreactor.automations import events
from pioreactor.automations.led import LEDSilent as Silent
from pioreactor.automations.led.light_dark_cycle import LightDarkCycle
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def pause(n=1) -> None:
    # to avoid race conditions when updating state
    time.sleep(n * 0.5)


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0, check_interval: float = 0.01) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(check_interval)
    return False


def test_silent() -> None:
    experiment = "test_silent"
    with Silent(duration=60, unit=unit, experiment=experiment) as ld:
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
        r = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/led_automation/automation_name", timeout=1)
        assert r is not None
        assert r.payload.decode() == "silent"
        assert ld.latest_normalized_od == 1.0
        assert ld.latest_growth_rate == 0.01


def test_we_respect_any_locks_on_leds_we_want_to_modify() -> None:
    experiment = "test_we_respect_any_locks_on_leds_we_want_to_modify"
    with local_intermittent_storage("led_locks") as cache:
        for c in cache.iterkeys():
            cache.pop(c)

    with Silent(duration=1, unit=unit, experiment=experiment) as ld:
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
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=60 * 16,
        dark_duration_minutes=8 * 60,
        unit=unit,
        experiment=experiment,
    ) as lc:
        assert wait_for(lambda: lc.light_active)
        with local_intermittent_storage("leds") as c:
            assert c["D"] == 50
            assert c["C"] == 50


def test_light_dark_cycle_turns_off_after_N_cycles() -> None:
    experiment = "test_light_dark_cycle_turns_off_after_N_cycles"
    unit = get_unit_name()
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=60 * 16,
        dark_duration_minutes=8 * 60,
        unit=unit,
        experiment=experiment,
    ) as lc:
        assert wait_for(lambda: lc.light_active)
        lc.trigger_leds(16 * 60)

        assert not lc.light_active
        with local_intermittent_storage("leds") as c:
            assert c["D"] == 0.0
            assert c["C"] == 0.0


def test_dark_duration_hour_to_zero() -> None:
    experiment = "test_dark_duration_hour_to_zero"
    unit = get_unit_name()
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=60 * 16,
        dark_duration_minutes=8 * 60,
        unit=unit,
        experiment=experiment,
    ) as lc:
        assert wait_for(lambda: lc.light_active)
        lc.trigger_leds(16 * 60)

        assert not lc.light_active
        lc.set_dark_duration_minutes(0 * 60)
        assert lc.light_active

        with local_intermittent_storage("leds") as c:
            assert c["D"] == 50.0
            assert c["C"] == 50.0


def test_light_duration_hour_to_zero() -> None:
    experiment = "test_light_duration_hour_to_zero"
    unit = get_unit_name()
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=60 * 16,
        dark_duration_minutes=8 * 60,
        unit=unit,
        experiment=experiment,
    ) as lc:
        assert wait_for(lambda: lc.light_active)

        lc.set_light_duration_minutes(60 * 0)

        assert not lc.light_active


def test_add_dark_duration_minutes() -> None:
    experiment = "test_add_dark_duration_minutes * 60"
    unit = get_unit_name()
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=60 * 16,
        dark_duration_minutes=8 * 60,
        unit=unit,
        experiment=experiment,
    ) as lc:
        assert wait_for(lambda: lc.light_active)
        lc.trigger_leds(16 * 60)
        assert not lc.light_active

        lc._cycle_started_at = current_utc_datetime() - timedelta(minutes=16 * 60)
        lc.set_dark_duration_minutes(10 * 60)

        assert not lc.light_active

        with local_intermittent_storage("leds") as c:
            assert c["D"] == 0.0
            assert c["C"] == 0.0


def test_remove_dark_duration_minutes() -> None:
    experiment = "test_remove_dark_duration_minutes * 60"
    unit = get_unit_name()
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=60 * 16,
        dark_duration_minutes=8 * 60,
        unit=unit,
        experiment=experiment,
    ) as lc:
        assert wait_for(lambda: lc.light_active)
        lc.trigger_leds(20 * 60)

        assert not lc.light_active

        lc._cycle_started_at = current_utc_datetime() - timedelta(minutes=20 * 60)
        lc.set_dark_duration_minutes(3 * 60)

        assert lc.light_active

        with local_intermittent_storage("leds") as c:
            assert c["D"] == 50.0
            assert c["C"] == 50.0


def test_fractional_hours() -> None:
    experiment = "test_fractional_hours"
    unit = get_unit_name()
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=60 * 0.9,  # type: ignore
        dark_duration_minutes=0.1 * 60,  # type: ignore
        unit=unit,
        experiment=experiment,
    ) as lc:
        lc.trigger_leds(10)
        assert lc.light_active

        lc.trigger_leds(55)
        assert not lc.light_active

        lc.trigger_leds(62)
        assert lc.light_active


def test_light_dark_cycle_supports_sub_minute_phase_schedule() -> None:
    experiment = "test_light_dark_cycle_supports_sub_minute_phase_schedule"
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=0.01,
        dark_duration_minutes=0.01,
        unit=get_unit_name(),
        experiment=experiment,
    ) as lc:
        assert wait_for(lambda: lc.light_active)
        assert wait_for(lambda: not lc.light_active, timeout=2.0)


@pytest.mark.slow
def test_light_dark_cycle_alternates_every_six_seconds_for_tenth_minute_phases() -> None:
    experiment = "test_light_dark_cycle_alternates_every_six_seconds_for_tenth_minute_phases"
    with LightDarkCycle(
        light_intensity=50,
        light_duration_minutes=0.1,
        dark_duration_minutes=0.1,
        unit=get_unit_name(),
        experiment=experiment,
    ) as lc:
        transitions: list[tuple[bool, float]] = []

        assert wait_for(lambda: lc.light_active)
        transitions.append((lc.light_active, time.monotonic()))

        for expected_light_active in [False, True, False, True, False]:
            assert wait_for(lambda: lc.light_active is expected_light_active, timeout=8.0)
            transitions.append((lc.light_active, time.monotonic()))

    assert [state for state, _ in transitions] == [True, False, True, False, True, False]
    phase_durations = [
        current_timestamp - previous_timestamp
        for (_, previous_timestamp), (_, current_timestamp) in zip(transitions, transitions[1:])
    ]
    assert phase_durations == pytest.approx([6.0] * 5, abs=1.0)


@pytest.fixture
def light_dark_cycle():
    # Use context manager so each test tears down the automation cleanly.
    with LightDarkCycle(
        unit=get_unit_name(),
        experiment="test_light_dark_cycle",
        light_intensity=100,
        light_duration_minutes=60,
        dark_duration_minutes=60,
    ) as cycle:
        yield cycle


def test_light_turns_on_in_light_period(light_dark_cycle) -> None:
    light_dark_cycle.light_active = False

    # In this case, light should be turned on
    event = light_dark_cycle.trigger_leds(30)

    # Check that the LEDs were turned on
    assert isinstance(event, events.ChangedLedIntensity)
    assert event.message is not None
    assert "turned on LEDs" in event.message
    assert light_dark_cycle.light_active


def test_light_stays_on_in_light_period(light_dark_cycle) -> None:
    light_dark_cycle.light_active = True

    # In this case, light should stay on
    event = light_dark_cycle.trigger_leds(30)

    # Check that no change in LED status occurred
    assert event is None


def test_light_turns_off_in_dark_period(light_dark_cycle) -> None:
    # Setting the minutes to 60 (inside the dark period of 1 hour, after the light period of 1 hour)
    light_dark_cycle.light_active = True

    # In this case, light should be turned off
    event = light_dark_cycle.trigger_leds(60)

    # Check that the LEDs were turned off
    assert isinstance(event, events.ChangedLedIntensity)
    assert event.message is not None
    assert "turned off LEDs" in event.message
    assert not light_dark_cycle.light_active


def test_light_stays_off_in_dark_period(light_dark_cycle) -> None:
    light_dark_cycle.light_active = False

    # In this case, light should stay off
    event = light_dark_cycle.trigger_leds(90)

    # Check that no change in LED status occurred
    assert event is None
