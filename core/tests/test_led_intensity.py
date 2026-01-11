# -*- coding: utf-8 -*-
import pytest
from click.testing import CliRunner
from pioreactor.actions.led_intensity import ALL_LED_CHANNELS
from pioreactor.actions.led_intensity import change_leds_intensities_temporarily
from pioreactor.actions.led_intensity import is_led_channel_locked
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.actions.led_intensity import LedChannel
from pioreactor.actions.led_intensity import lock_leds_temporarily
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_unit_name


def test_lock_will_prevent_led_from_updating() -> None:
    channel: LedChannel = "A"

    unit = get_unit_name()
    exp = "test_lock_will_prevent_led_from_updating"

    assert led_intensity({"A": 20}, unit=unit, experiment=exp)

    with lock_leds_temporarily([channel]):
        assert not led_intensity({"A": 10}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache[channel]) == 20


def test_lock_will_prevent_led_from_updating_single_channel_but_not_others_passed_in() -> None:
    unit = get_unit_name()
    exp = "test_lock_will_prevent_led_from_updating_single_channel_but_not_others_passed_in"

    assert led_intensity({"A": 20, "B": 20}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == 20
        assert float(cache["A"]) == 20

    with lock_leds_temporarily(["A"]):
        assert not led_intensity({"A": 10, "B": 10}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == 10
        assert float(cache["A"]) == 20


def test_change_leds_intensities_temporarily() -> None:
    unit = get_unit_name()
    exp = "test_change_leds_intensities_temporarily"

    original_settings: dict[LedChannel, float] = {"A": 20, "B": 20, "D": 1.0, "C": 0.0}
    led_intensity(original_settings, unit=unit, experiment=exp)

    with change_leds_intensities_temporarily({"A": 10}, unit=unit, experiment=exp):
        with local_intermittent_storage("leds") as cache:
            assert float(cache["A"]) == 10
            assert float(cache["B"]) == original_settings["B"]

    with local_intermittent_storage("leds") as cache:
        assert float(cache["A"]) == original_settings["A"]
        assert float(cache["B"]) == original_settings["B"]
        assert float(cache["C"]) == original_settings["C"]
        assert float(cache["D"]) == original_settings["D"]

    with change_leds_intensities_temporarily({"A": 10, "C": 10, "D": 0}, unit=unit, experiment=exp):
        with local_intermittent_storage("leds") as cache:
            assert float(cache["A"]) == 10
            assert float(cache["B"]) == original_settings["B"]
            assert float(cache["C"]) == 10
            assert float(cache["D"]) == 0

    with local_intermittent_storage("leds") as cache:
        assert float(cache["A"]) == original_settings["A"]
        assert float(cache["B"]) == original_settings["B"]
        assert float(cache["C"]) == original_settings["C"]
        assert float(cache["D"]) == original_settings["D"]

    with change_leds_intensities_temporarily({}, unit=unit, experiment=exp):
        with local_intermittent_storage("leds") as cache:
            assert float(cache["A"]) == original_settings["A"]
            assert float(cache["B"]) == original_settings["B"]
            assert float(cache["C"]) == original_settings["C"]
            assert float(cache["D"]) == original_settings["D"]


def test_local_cache_is_updated() -> None:
    channel: LedChannel = "B"

    unit = get_unit_name()
    exp = "test_local_cache_is_updated"

    assert led_intensity({channel: 20}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        assert float(cache[channel]) == 20


def test_led_intensity_can_be_killed_by_pio_kill() -> None:
    from pioreactor.actions.led_intensity import click_led_intensity
    from pioreactor.cli.pio import kill

    runner = CliRunner()
    runner.invoke(click_led_intensity, ["--A", "10"])

    result = runner.invoke(kill, ["--job-name", "led_intensity"])
    assert result.output.strip() == "Killed 1 job."


def test_invalid_channel_leaves_state_unchanged_and_returns_false() -> None:
    unit = get_unit_name()
    exp = "test_invalid_channel_leaves_state_unchanged"

    # initialize a known state for channel A
    assert led_intensity({"A": 50}, unit=unit, experiment=exp)
    with local_intermittent_storage("leds") as cache:
        initial_a = float(cache["A"])

    # attempt to set an invalid channel
    assert not led_intensity({"Z": 10.0}, unit=unit, experiment=exp)  # type: ignore
    with local_intermittent_storage("leds") as cache:
        # channel A remains unchanged, and invalid channel Z is not added
        assert float(cache["A"]) == initial_a
        assert "Z" not in cache


def test_invalid_intensity_leaves_state_unchanged_and_returns_false() -> None:
    unit = get_unit_name()
    exp = "test_invalid_intensity_leaves_state_unchanged"

    # initialize a known state for channel B
    assert led_intensity({"B": 60}, unit=unit, experiment=exp)
    with local_intermittent_storage("leds") as cache:
        initial_b = float(cache["B"])

    # attempt to set out-of-range intensities
    assert not led_intensity({"B": -1}, unit=unit, experiment=exp)
    assert not led_intensity({"B": 200}, unit=unit, experiment=exp)
    with local_intermittent_storage("leds") as cache:
        assert float(cache["B"]) == initial_b


def test_is_led_channel_locked_directly() -> None:
    # Test is_led_channel_locked and lock_leds_temporarily behavior
    assert not is_led_channel_locked("A")

    with lock_leds_temporarily(["A"]):
        assert is_led_channel_locked("A")

    assert not is_led_channel_locked("A")


def test_change_leds_intensities_temporarily_invalid_raises_and_state_unchanged() -> None:
    unit = get_unit_name()
    exp = "test_change_leds_invalid"

    # Initialize a valid state for channel A
    assert led_intensity({"A": 30}, unit=unit, experiment=exp)

    with local_intermittent_storage("leds") as cache:
        before = {c: float(cache.get(c, 0.0)) for c in ALL_LED_CHANNELS}

    # Attempt to use invalid intensity inside context manager
    with pytest.raises(ValueError):
        with change_leds_intensities_temporarily({"A": -10}, unit=unit, experiment=exp):
            pass

    # State should remain unchanged after failure
    with local_intermittent_storage("leds") as cache:
        after = {c: float(cache.get(c, 0.0)) for c in ALL_LED_CHANNELS}

    assert after == before


def test_led_intensity_sets_storage_and_defaults_unmodified_channels() -> None:
    # Apply intensities to some channels and verify storage reflects those values
    result = led_intensity({"A": 10.0, "C": 30.5}, verbose=False, source_of_event="test")
    assert result is True
    with local_intermittent_storage("leds") as cache:
        # Modified channels
        assert cache["A"] == pytest.approx(10.0)
        assert cache["C"] == pytest.approx(30.5)


@pytest.mark.parametrize(
    "desired_state",
    [
        {"Z": 5.0},  # invalid channel
        {"A": -1.0},  # intensity below range
        {"B": 101.0},  # intensity above range
    ],
)
def test_led_intensity_invalid_inputs_do_not_modify_storage(desired_state) -> None:
    # Invalid channel names or out-of-range intensities should return False and not touch cache
    result = led_intensity(desired_state, verbose=False, source_of_event="test")
    assert result is False
    with local_intermittent_storage("leds") as cache:
        # Storage should remain empty or default for all channels
        for channel in ALL_LED_CHANNELS:
            # If present, values should be default
            assert cache.get(channel, 0.0) == pytest.approx(0.0)
