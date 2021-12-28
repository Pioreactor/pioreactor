# -*- coding: utf-8 -*-
# pump calibration
from __future__ import annotations

from typing import Callable
import json
import click
import time
from pioreactor.utils import publish_ready_to_disconnected_state, local_persistant_storage
from pioreactor.config import config
from pioreactor.actions.add_media import add_media
from pioreactor.actions.remove_waste import remove_waste
from pioreactor.actions.add_alt_media import add_alt_media
from pioreactor.utils.math_helpers import simple_linear_regression
from pioreactor.utils.timing import current_utc_time
from pioreactor.whoami import (
    get_unit_name,
    get_latest_experiment_name,
    get_latest_testing_experiment_name,
)
from pioreactor.logging import create_logger


def which_pump_are_you_calibrating():
    media_timestamp, missing_media = "", True
    waste_timestamp, missing_waste = "", True
    alt_media_timestamp, missing_alt_media = "", True

    with local_persistant_storage("pump_calibration") as cache:
        missing_media = "media_ml_calibration" not in cache
        missing_waste = "waste_ml_calibration" not in cache
        missing_alt_media = "alt_media_ml_calibration" not in cache

        if not missing_media:
            media_timestamp = json.loads(cache["media_ml_calibration"])["timestamp"][:10]

        if not missing_waste:
            waste_timestamp = json.loads(cache["waste_ml_calibration"])["timestamp"][:10]

        if not missing_alt_media:
            alt_media_timestamp = json.loads(cache["alt_media_ml_calibration"])[
                "timestamp"
            ][:10]

    r = click.prompt(
        click.style(
            f"""Which pump are you calibrating?
1. Media       {'[missing calibration]' if missing_media else f'[last ran {media_timestamp}]'}
2. Alt-media   {'[missing calibration]' if missing_alt_media else f'[last ran {alt_media_timestamp}]'}
3. Waste       {'[missing calibration]' if missing_waste else f'[last ran {waste_timestamp}]'}
""",
            fg="green",
        ),
        type=click.Choice(["1", "2", "3"]),
        show_choices=True,
    )

    if r == "1":
        if not missing_media:
            click.confirm(
                click.style("Confirm over-writting existing calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("media", add_media)
    elif r == "2":
        if not missing_alt_media:
            click.confirm(
                click.style("Confirm over-writting existing calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("alt_media", add_alt_media)
    elif r == "3":
        if not missing_waste:
            click.confirm(
                click.style("Confirm over-writting existing calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("waste", remove_waste)


def setup(pump_name: str, execute_pump: Callable, hz: float, dc: float) -> None:
    # set up...

    click.clear()
    click.echo()
    click.echo("We need to prime the pump by filling the tubes completely with water.")
    click.echo("Connecting the tubes to the pump, and fill a container with water.")
    click.echo(
        "Place free ends of the tube into the water. Make sure the pump's power is connected to "
        + click.style(f"PWM channel {config.get('PWM_reverse', pump_name)}.", bold=True)
    )
    click.echo("We'll run the pumps continuously until the tubes are filled.")
    click.echo(
        click.style("Press CTRL+C when the tubes are fully filled with water.", bold=True)
    )

    while not click.confirm(click.style("Ready?", fg="green")):
        pass

    try:
        execute_pump(
            duration=10000,
            source_of_event="pump_calibration",
            unit=get_unit_name(),
            experiment=get_latest_testing_experiment_name(),
            calibration={"duration_": 1.0, "hz": hz, "dc": dc, "bias_": 0},
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
        click.style("Enter frequency of PWM. [enter] for default 100hz", fg="green"),
        type=click.FloatRange(0, 10000),
        default=100,
        show_default=False,
    )
    dc = click.prompt(
        click.style("Enter duty cycle percent. [enter] for default 66%", fg="green"),
        type=click.FloatRange(0, 100),
        default=66,
        show_default=False,
    )

    return hz, dc


def run_tests(
    execute_pump: Callable, hz: float, dc: float
) -> tuple[list[float], list[float]]:
    click.clear()
    click.echo()
    click.echo("Beginning tests.")
    results = []
    durations_to_test = [0.5, 0.5, 0.5, 0.5, 1.5, 1.5, 1.5, 1.5]
    for duration in durations_to_test:

        click.echo(
            "We will run the pump for a set amount of time (in seconds), and you will measure how much liquid is expelled."
        )
        click.echo(
            "You can either use an accurate weighing scale, or a graduated cylinder (recall that 1 g = 1 ml water)."
        )
        while not click.confirm(click.style(f"Ready to test {duration}s?", fg="green")):
            pass

        execute_pump(
            duration=duration,
            source_of_event="pump_calibration",
            unit=get_unit_name(),
            experiment=get_latest_testing_experiment_name(),
            calibration={"duration_": 1.0, "hz": hz, "dc": dc, "bias_": 0},
        )
        r = click.prompt(
            click.style("Enter amount of water expelled", fg="green"),
            type=click.FLOAT,
            confirmation_prompt=click.style("Repeat for confirmation", fg="green"),
        )
        results.append(r)
        click.clear()
        click.echo()

    return durations_to_test, results


def pump_calibration() -> None:

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    logger = create_logger("pump_calibration", unit=unit, experiment=experiment)
    logger.info("Starting pump calibration.")

    with publish_ready_to_disconnected_state(unit, experiment, "pump_calibration"):

        click.clear()
        click.echo()
        pump_name, execute_pump = which_pump_are_you_calibrating()

        hz, dc = choose_settings()

        setup(pump_name, execute_pump, hz, dc)
        durations, volumes = run_tests(execute_pump, hz, dc)

        (slope, std_slope), (bias, std_bias) = simple_linear_regression(
            durations, volumes
        )

        # check parameters for problems
        if slope < 0:
            logger.warning(
                "Slope is negative - you probably want to rerun this calibration..."
            )
        if slope / std_slope < 5.0:
            logger.warning(
                "Too much uncertainty in slope - you probably want to rerun this calibration..."
            )

        # save to cache
        with local_persistant_storage("pump_calibration") as cache:
            cache[f"{pump_name}_ml_calibration"] = json.dumps(
                {
                    "duration_": slope,
                    "hz": hz,
                    "dc": dc,
                    "bias_": bias,
                    "timestamp": current_utc_time(),
                }
            )

        logger.debug(
            f"slope={slope:0.3f} ± {std_slope:0.2f}, bias={bias:0.3f} ± {std_bias:0.2f}"
        )
        logger.info("Finished pump calibration.")


@click.command(name="pump_calibration")
def click_pump_calibration():
    pump_calibration()
