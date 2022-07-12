# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from typing import Callable

import click
from msgspec.json import decode
from msgspec.json import encode

from pioreactor import structs
from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import remove_waste
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.math_helpers import (
    simple_linear_regression_with_forced_nil_intercept, correlation
)
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_latest_testing_experiment_name
from pioreactor.whoami import get_unit_name


def which_pump_are_you_calibrating():
    media_timestamp, has_media = "", True
    waste_timestamp, has_waste = "", True
    alt_media_timestamp, has_alt_media = "", True

    with local_persistant_storage("pump_calibration") as cache:
        has_media = "media_ml_calibration" in cache
        has_waste = "waste_ml_calibration" in cache
        has_alt_media = "alt_media_ml_calibration" in cache

        if has_media:
            media_timestamp = decode(
                cache["media_ml_calibration"], type=structs.PumpCalibration
            ).timestamp[:10]

        if has_waste:
            waste_timestamp = decode(
                cache["waste_ml_calibration"], type=structs.PumpCalibration
            ).timestamp[:10]

        if has_alt_media:
            alt_media_timestamp = decode(
                cache["alt_media_ml_calibration"], type=structs.PumpCalibration
            ).timestamp[:10]

    r = click.prompt(
        click.style(
            f"""Which pump are you calibrating?
1. Media       {f'[last ran {media_timestamp}]' if has_media else '[missing calibration]'}
2. Alt-media   {f'[last ran {alt_media_timestamp}]' if has_alt_media else '[missing calibration]'}
3. Waste       {f'[last ran {waste_timestamp}]' if has_waste else '[missing calibration]'}
""",
            fg="green",
        ),
        type=click.Choice(["1", "2", "3"]),
        show_choices=True,
    )

    if r == "1":
        if has_media:
            click.confirm(
                click.style("Confirm over-writing existing calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("media", add_media)
    elif r == "2":
        if has_alt_media:
            click.confirm(
                click.style("Confirm over-writing existing calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("alt_media", add_alt_media)
    elif r == "3":
        if has_waste:
            click.confirm(
                click.style("Confirm over-writing existing calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("waste", remove_waste)

def setup(pump_name: str, execute_pump: Callable, hz: float, dc: float) -> None:
    # set up...

    click.clear()
    click.echo()
    click.echo("We need to prime the pump by filling the tubes completely with water.")
    click.echo("1. Fill a container with water.")
    click.echo("2. Place free ends of the tube into the water.")
    click.echo(
        "Make sure the pump's power is connected to "
        + click.style(f"PWM channel {config.get('PWM_reverse', pump_name)}.", bold=True)
    )
    click.echo("We'll run the pumps continuously until the tubes are filled.")
    click.echo(
        click.style("3. Press CTRL+C when the tubes are fully filled with water.", bold=True)
    )

    while not click.confirm(click.style("Ready?", fg="green")):
        pass

    try:
        execute_pump(
            duration=10000,
            source_of_event="pump_calibration",
            unit=get_unit_name(),
            experiment=get_latest_testing_experiment_name(),
            calibration=structs.PumpCalibration(
                duration_=1.0,
                hz=hz,
                dc=dc,
                bias_=0,
                timestamp=current_utc_timestamp(),
                voltage=-1.0,
            ),
        )
    except KeyboardInterrupt:
        pass

    click.echo()

    time.sleep(0.5)  # pure UX
    return


def choose_settings() -> tuple[float, float]:
    click.clear()
    click.echo()
    hz = click.prompt(
        click.style("Enter frequency of PWM. [enter] for default 200 hz", fg="green"),
        type=click.FloatRange(0, 10000),
        default=200,
        show_default=False,
    )
    dc = click.prompt(
        click.style("Enter duty cycle percent as a whole number. [enter] for default 90%", fg="green"),
        type=click.IntRange(0, 100),
        default=90,
        show_default=False,
    )

    return hz, dc


def run_tests(
    execute_pump: Callable, hz: float, dc: float, min_duration: float, max_duration: float
) -> tuple[list[float], list[float]]:
    click.clear()
    click.echo()
    click.echo("Beginning tests.")
    results = []
    durations_to_test = [
        min_duration,
        min_duration * 1.1,
        min_duration * 1.2,
        min_duration * 1.3,
    ] + [max_duration * 0.85, max_duration * 0.90, max_duration * 0.95, max_duration]
    for i, duration in enumerate(durations_to_test):
        while True:

            if i > 0:
                click.echo("Remove the water from the measuring container or tare your weighing scale.")

            click.echo(
                "We will run the pump for a set amount of time, and you will measure how much liquid is expelled."
            )
            click.echo(
                "Use a small container placed on top of an accurate weighing scale."
            )
            click.echo("Hold the end of the outflow tube above so the container catches the expelled liquid.")
            while not click.confirm(click.style(f"Ready to test {duration:.2f}s?", fg="green")):
                pass

            execute_pump(
                duration=duration,
                source_of_event="pump_calibration",
                unit=get_unit_name(),
                experiment=get_latest_testing_experiment_name(),
                calibration=structs.PumpCalibration(
                    duration_=1.0,
                    hz=hz,
                    dc=dc,
                    bias_=0,
                    timestamp=current_utc_timestamp(),
                    voltage=-1.0,
                ),
            )
            r = click.prompt(
                click.style("Enter amount of water expelled, or REDO", fg="green"),
                confirmation_prompt=click.style("Repeat for confirmation", fg="green"),
            )
            if r == "REDO":
                click.clear()
                click.echo()
                continue

            try:
                results.append(float(r))
                click.clear()
                click.echo()
                break
            except ValueError:
                click.echo("Not a number - retrying.")


    return durations_to_test, results


def pump_calibration(min_duration: float, max_duration: float) -> None:

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    logger = create_logger("pump_calibration", unit=unit, experiment=experiment)
    logger.info("Starting pump calibration.")

    with publish_ready_to_disconnected_state(unit, experiment, "pump_calibration"):

        click.clear()
        click.echo()
        pump_name, execute_pump = which_pump_are_you_calibrating()

        is_ready = True
        while is_ready:
            hz, dc = choose_settings()
            setup(pump_name, execute_pump, hz, dc)

            is_ready = click.confirm(
                click.style("Do you want to change the frequency or duty cycle?", fg="green"),
                prompt_suffix=" ",
                default=False,
            )

        durations, volumes = run_tests(execute_pump, hz, dc, min_duration, max_duration)

        (slope, std_slope), (
            bias,
            std_bias,
        ) = simple_linear_regression_with_forced_nil_intercept(durations, volumes)

        # check parameters for problems
        if correlation(durations, volumes) < 0:
            logger.warning("Correlation is negative - you probably want to rerun this calibration...")
        if slope / std_slope < 5.0:
            logger.warning(
                "Too much uncertainty in slope - you probably want to rerun this calibration..."
            )

        # save to cache
        with local_persistant_storage("pump_calibration") as cache:
            cache[f"{pump_name}_ml_calibration"] = encode(
                structs.PumpCalibration(
                    duration_=slope,
                    hz=hz,
                    dc=dc,
                    bias_=bias,
                    timestamp=current_utc_timestamp(),
                    voltage=-1.0,
                )
            )
            cache[f"{pump_name}_calibration_data"] = encode(
                {
                    "timestamp": current_utc_timestamp(),
                    "data": {"durations": durations, "volumes": volumes},
                }
            )

        logger.debug(f"slope={slope:0.2f} ± {std_slope:0.2f}, bias={bias:0.2f} ± {std_bias:0.2f}")

        logger.debug(
            f"Calibration is best for volumes between {(slope * min_duration + bias):0.1f}mL to {(slope * max_duration + bias):0.1f}mL, but will be okay for slightly outside this range too."
        )
        logger.info("Finished pump calibration.")


@click.option("--min-duration", type=float)
@click.option("--max-duration", type=float)
@click.command(name="pump_calibration")
def click_pump_calibration(min_duration, max_duration):
    """
    Calibrate a pump
    """

    if max_duration is None and min_duration is None:
        min_duration, max_duration = 0.45, 1.25
    elif (max_duration is not None) and (min_duration is not None):
        assert min_duration < max_duration, "min_duration >= max_duration"
    else:
        raise ValueError("min_duration and max_duration must both be set.")

    pump_calibration(min_duration, max_duration)
