# -*- coding: utf-8 -*-
"""
https://docs.pioreactor.com/developer-guide/adding-calibration-type

This should have used calibration_type as the keys, but instead it uses media, alt_media, and waste..
"""
from __future__ import annotations

import time
from typing import Callable
from typing import Optional
from typing import Type

import click
from msgspec.json import decode
from msgspec.json import encode

from pioreactor import structs
from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import remove_waste
from pioreactor.config import config
from pioreactor.config import leader_address
from pioreactor.hardware import voltage_in_aux
from pioreactor.logging import create_logger
from pioreactor.mureq import patch
from pioreactor.mureq import put
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.math_helpers import correlation
from pioreactor.utils.math_helpers import simple_linear_regression_with_forced_nil_intercept
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_latest_testing_experiment_name
from pioreactor.whoami import get_unit_name


def introduction() -> None:
    import logging

    logging.disable(logging.WARNING)

    click.clear()
    click.echo(
        """This routine will calibrate the pumps on your current Pioreactor. You'll need:

    1. A Pioreactor
    2. A vial placed on a scale with accuracy at least 0.1g
       OR an accurate graduated cylinder.
    3. A larger container filled with water
    4. A pump connected to the correct PWM channel (1, 2, 3, or 4) as determined in your Configurations.

We will dose for a set duration, you'll measure how much volume was expelled, and then record it back here. After doing this a few times, we can construct a calibration line for this pump.
"""
    )
    click.confirm(click.style("Ready?", fg="green"))
    click.clear()


def get_metadata_from_user(pump_type) -> str:
    with local_persistant_storage("pump_calibrations") as cache:
        while True:
            name = click.prompt(
                click.style(
                    f"Optional: Provide a name for this calibration. [enter] to use default name `{pump_type}-{current_utc_datestamp()}`",
                    fg="green",
                ),
                type=str,
                default=f"{pump_type}-{current_utc_datestamp()}",
                show_default=False,
            ).strip()
            if name == "":
                click.echo("Name cannot be empty")
                continue
            elif name in cache:
                if click.confirm(
                    click.style("❗️ Name already exists. Do you wish to overwrite?", fg="green")
                ):
                    break
            elif name == "current":
                click.echo("Name cannot be `current`.")
                continue
            else:
                break
    return name


def which_pump_are_you_calibrating() -> tuple[str, Callable]:
    with local_persistant_storage("current_pump_calibration") as cache:
        has_media = "media" in cache
        has_waste = "waste" in cache
        has_alt_media = "alt_media" in cache

        if has_media:
            media_timestamp = decode(cache["media"], type=structs.MediaPumpCalibration).created_at
            media_name = decode(cache["media"], type=structs.MediaPumpCalibration).name

        if has_waste:
            waste_timestamp = decode(cache["waste"], type=structs.WastePumpCalibration).created_at
            waste_name = decode(cache["waste"], type=structs.WastePumpCalibration).name

        if has_alt_media:
            alt_media_timestamp = decode(
                cache["alt_media"], type=structs.AltMediaPumpCalibration
            ).created_at
            alt_media_name = decode(cache["alt_media"], type=structs.AltMediaPumpCalibration).name

    click.secho("Step 1", fg="green", bold=True)
    r = click.prompt(
        click.style(
            f"""Which pump are you calibrating?
1. Media       {f'[{media_name}, last ran {media_timestamp:%d %b, %Y}]' if has_media else '[No calibration]'}
2. Alt-media   {f'[{alt_media_name}, last ran {alt_media_timestamp:%d %b, %Y}]' if has_alt_media else '[No calibration]'}
3. Waste       {f'[{waste_name}, last ran {waste_timestamp:%d %b, %Y}]' if has_waste else '[No calibration]'}
""",
            fg="green",
        ),
        type=click.Choice(["1", "2", "3"]),
        show_choices=True,
    )

    if r == "1":
        if has_media:
            click.confirm(
                click.style("Confirm replacing current calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("media", add_media)
    elif r == "2":
        if has_alt_media:
            click.confirm(
                click.style("Confirm replacing current calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("alt_media", add_alt_media)
    elif r == "3":
        if has_waste:
            click.confirm(
                click.style("Confirm replacing current calibration?", fg="green"),
                abort=True,
                prompt_suffix=" ",
            )
        return ("waste", remove_waste)
    else:
        raise ValueError()


def setup(pump_type: str, execute_pump: Callable, hz: float, dc: float, unit: str) -> None:
    # set up...
    try:
        channel_pump_is_configured_for = config.get("PWM_reverse", pump_type)
    except KeyError:
        click.echo(
            f"❌ {pump_type} is not present in config.ini. Please add it to the [PWM] section and try again."
        )
        raise click.Abort()
    click.clear()
    click.echo()
    click.secho("Step 2", fg="green", bold=True)
    click.echo("We need to prime the pump by filling the tubes completely with water.")
    click.echo("1. Fill a container with water.")
    click.echo("2. Submerge both ends of the pump's tubes into the water.")
    click.echo(
        "Make sure the pump's power is connected to "
        + click.style(f"PWM channel {channel_pump_is_configured_for}.", bold=True)
    )
    click.echo("We'll run the pumps continuously until the tubes are completely filled with water.")
    click.echo()

    while not click.confirm(click.style("Ready to start pumping?", fg="green")):
        pass

    click.secho("Press CTRL+C when the tubes are completely filled with water.", bold=True)

    try:
        execute_pump(
            continuously=True,
            source_of_event="pump_calibration",
            unit=get_unit_name(),
            experiment=get_latest_testing_experiment_name(),
            calibration=structs.PumpCalibration(
                name="calibration",
                created_at=current_utc_datetime(),
                pump=pump_type,
                duration_=1.0,
                hz=hz,
                dc=dc,
                bias_=0,
                voltage=voltage_in_aux(),
                pioreactor_unit=unit,
            ),
        )
    except KeyboardInterrupt:
        pass

    click.echo()

    time.sleep(0.5)  # pure UX
    return


def choose_settings() -> tuple[float, float]:
    hz = click.prompt(
        click.style("Optional: Enter frequency of PWM. [enter] for default 250 hz", fg="green"),
        type=click.FloatRange(0.1, 10000),
        default=250,
        show_default=False,
    )
    dc = click.prompt(
        click.style(
            "Optional: Enter duty cycle percent as a whole number. [enter] for default 95%",
            fg="green",
        ),
        type=click.IntRange(0, 100),
        default=95,
        show_default=False,
    )

    return hz, dc


def plot_data(
    x, y, title, x_min=None, x_max=None, interpolation_curve=None, highlight_recent_point=True
):
    import plotext as plt  # type: ignore

    plt.clf()

    if interpolation_curve:
        plt.plot(x, [interpolation_curve(x_) for x_ in x], color=204)

    plt.scatter(x, y)

    if highlight_recent_point:
        plt.scatter([x[-1]], [y[-1]], color=204)

    plt.theme("pro")
    plt.title(title)
    plt.plot_size(105, 20)
    plt.xlim(x_min, x_max)
    plt.show()


def run_tests(
    execute_pump: Callable,
    hz: float,
    dc: float,
    min_duration: float,
    max_duration: float,
    pump_type: str,
    unit: str,
) -> tuple[list[float], list[float]]:
    click.clear()
    click.echo()
    click.secho("Step 3", fg="green", bold=True)
    click.echo("Beginning tests.")

    empty_calibration = structs.PumpCalibration(
        name="_test",
        duration_=1.0,
        pump=pump_type,
        hz=hz,
        dc=dc,
        bias_=0,
        created_at=current_utc_datetime(),
        voltage=voltage_in_aux(),
        pioreactor_unit=unit,
    )

    results: list[float] = []
    durations_to_test = (
        [min_duration] * 4 + [(min_duration + max_duration) / 2] * 2 + [max_duration] * 4
    )
    n_samples = len(durations_to_test)

    for i, duration in enumerate(durations_to_test):
        while True:
            if i != 0:
                plot_data(
                    durations_to_test[:i],
                    results,
                    title="Pump Calibration (ongoing)",
                    x_min=min_duration,
                    x_max=max_duration,
                )

            if i > 0:
                click.echo()
                click.echo(
                    "Remove the water from the measuring container or tare your weighing scale."
                )

            click.echo(
                "We will run the pump for a set amount of time, and you will measure how much liquid is expelled."
            )
            click.echo("Use a small container placed on top of an accurate weighing scale.")
            click.echo(
                "Hold the end of the outflow tube above so the container catches the expelled liquid."
            )
            click.echo()
            click.secho(
                f"Test {i+1} of {n_samples} [{'#' * (i+1) }{' ' * (n_samples - i - 1)}]", fg="green"
            )
            while not click.confirm(click.style(f"Ready to test {duration:.2f}s?", fg="green")):
                pass

            execute_pump(
                duration=duration,
                source_of_event="pump_calibration",
                unit=get_unit_name(),
                experiment=get_latest_testing_experiment_name(),
                calibration=empty_calibration,
            )

            r = click.prompt(
                click.style("Enter amount of water expelled (g or ml), or REDO", fg="green"),
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


def save_results(
    name: str,
    pump_type: str,
    duration_: float,
    bias_: float,
    hz: float,
    dc: float,
    voltage: float,
    durations: list[float],
    volumes: list[float],
    unit: str,
) -> structs.PumpCalibration:
    struct: Type[structs.AnyPumpCalibration]

    if pump_type == "media":
        struct = structs.MediaPumpCalibration
    elif pump_type == "waste":
        struct = structs.WastePumpCalibration
    elif pump_type == "alt_media":
        struct = structs.AltMediaPumpCalibration
    else:
        raise ValueError()

    pump_calibration_result = struct(
        name=name,
        pioreactor_unit=unit,
        created_at=current_utc_datetime(),
        pump=pump_type,
        duration_=duration_,
        bias_=bias_,
        hz=hz,
        dc=dc,
        voltage=voltage_in_aux(),
        durations=durations,
        volumes=volumes,
    )

    # save to cache
    with local_persistant_storage("pump_calibrations") as cache:
        cache[name] = encode(pump_calibration_result)

    publish_to_leader(name)
    change_current(name)

    return pump_calibration_result


def publish_to_leader(name: str) -> bool:
    success = True

    with local_persistant_storage("pump_calibrations") as all_calibrations:
        calibration_result = decode(
            all_calibrations[name], type=structs.subclass_union(structs.PumpCalibration)
        )

    try:
        res = put(
            f"http://{leader_address}/api/calibrations",
            encode(calibration_result),
            headers={"Content-Type": "application/json"},
        )
        res.raise_for_status()
    except Exception:
        success = False
    if not success:
        click.echo(f"❌ Could not publish on leader at http://{leader_address}/api/calibrations")
    return success


def pump_calibration(min_duration: float, max_duration: float) -> None:
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    logger = create_logger("pump_calibration", unit=unit, experiment=experiment)
    logger.info("Starting pump calibration.")

    with publish_ready_to_disconnected_state(unit, experiment, "pump_calibration"):
        introduction()
        pump_type, execute_pump = which_pump_are_you_calibrating()
        name = get_metadata_from_user(pump_type)

        is_ready = True
        while is_ready:
            hz, dc = choose_settings()
            setup(pump_type, execute_pump, hz, dc, unit)

            is_ready = click.confirm(
                click.style("Do you want to change the frequency or duty cycle?", fg="green"),
                prompt_suffix=" ",
                default=False,
            )

        durations, volumes = run_tests(
            execute_pump, hz, dc, min_duration, max_duration, pump_type, unit
        )

        (slope, std_slope), (
            bias,
            std_bias,
        ) = simple_linear_regression_with_forced_nil_intercept(durations, volumes)

        plot_data(
            durations,
            volumes,
            title="Pump Calibration",
            x_min=min_duration,
            x_max=max_duration,
            interpolation_curve=curve_to_callable("poly", [slope, bias]),
            highlight_recent_point=False,
        )

        save_results(
            name=name,
            pump_type=pump_type,
            duration_=slope,
            bias_=bias,
            hz=hz,
            dc=dc,
            voltage=voltage_in_aux(),
            durations=durations,
            volumes=volumes,
            unit=unit,
        )

        click.echo(f"slope={slope:0.3f} ± {std_slope:0.3f}, bias={bias:0.3f} ± {std_bias:0.3f}")

        click.echo(
            f"Calibration is best for volumes between {(slope * min_duration + bias):0.2f}mL to {(slope * max_duration + bias):0.2f}mL, but will be okay for outside this range too."
        )

        # check parameters for problems
        if correlation(durations, volumes) < 0:
            logger.warning(
                "Correlation is negative - you probably want to rerun this calibration..."
            )
        if std_slope > 0.04:
            logger.warning(
                "Too much uncertainty in slope - you probably want to rerun this calibration..."
            )

        click.echo(f"Finished {pump_type} pump calibration.")


def curve_to_callable(curve_type: str, curve_data) -> Optional[Callable]:
    if curve_type == "poly":
        import numpy as np

        def curve_callable(x):
            return np.polyval(curve_data, x)

        return curve_callable

    else:
        return None


def display(name: str | None) -> None:
    from pprint import pprint

    def display_from_calibration_blob(pump_calibration: dict) -> None:
        volumes = pump_calibration["volumes"]
        durations = pump_calibration["durations"]
        name, pump = pump_calibration["name"], pump_calibration["pump"]
        plot_data(
            durations,
            volumes,
            title=f"Calibration for {pump} pump",
            highlight_recent_point=False,
            interpolation_curve=curve_to_callable(
                "poly", [pump_calibration["duration_"], pump_calibration["bias_"]]
            ),
        )
        click.echo(click.style(f"Data for {name}", underline=True, bold=True))
        pprint(pump_calibration)

    if name is not None:
        with local_persistant_storage("pump_calibrations") as c:
            display_from_calibration_blob(decode(c[name]))
    else:
        with local_persistant_storage("current_pump_calibration") as c:
            for pump in c.iterkeys():
                display_from_calibration_blob(decode(c[pump]))
                click.echo()
                click.echo()
                click.echo()


def change_current(name: str) -> bool:
    with local_persistant_storage("pump_calibrations") as all_calibrations:
        try:
            new_calibration = decode(
                all_calibrations[name], type=structs.subclass_union(structs.PumpCalibration)
            )  # decode name from list of all names
        except KeyError:
            create_logger("pump_calibration").error(
                f"Failed to swap. Calibration `{name}` not found."
            )
            raise click.Abort()

        pump_type_from_new_calibration = new_calibration.pump  # retrieve the pump type

        with local_persistant_storage("current_pump_calibration") as current_calibrations:
            if pump_type_from_new_calibration in current_calibrations:
                old_calibration = decode(
                    current_calibrations[pump_type_from_new_calibration],
                    type=structs.subclass_union(structs.PumpCalibration),
                )
            else:
                old_calibration = None

            current_calibrations[pump_type_from_new_calibration] = encode(new_calibration)

        try:
            res = patch(
                f"http://{leader_address}/api/calibrations/{get_unit_name()}/{new_calibration.type}/{new_calibration.name}",
                json={"current": 1},
            )
            res.raise_for_status()
        except Exception:
            click.echo(
                f"❌ Could not update on leader at http://{leader_address}/api/calibrations/{get_unit_name()}/{new_calibration.type}/{new_calibration.name}"
            )
            return False

        if old_calibration:
            click.echo(
                f"Replaced {old_calibration.name} with {new_calibration.name} as current calibration."
            )
        else:
            click.echo(f"Set {new_calibration.name} to current calibration.")
        return True


def list_():
    # get current calibrations
    current = []
    with local_persistant_storage("current_pump_calibration") as c:
        for pump in c.iterkeys():
            cal = decode(c[pump], type=structs.subclass_union(structs.PumpCalibration))
            current.append(cal.name)

    click.secho(
        f"{'Name':17s} {'Date':18s} {'Pump type':12s} {'Currently in use?':20s}",
        bold=True,
    )
    with local_persistant_storage("pump_calibrations") as c:
        for name in c.iterkeys():
            try:
                cal = decode(c[name], type=structs.subclass_union(structs.PumpCalibration))
                click.secho(
                    f"{cal.name:17s} {cal.created_at:%d %b, %Y}       {cal.pump:12s} {'✅' if cal.name in current else ''}",
                )
            except Exception as e:
                raise e


@click.group(invoke_without_command=True, name="pump_calibration")
@click.pass_context
@click.option("--min-duration", type=float)
@click.option("--max-duration", type=float)
def click_pump_calibration(ctx, min_duration, max_duration):
    """
    Calibrate a pump
    """
    if ctx.invoked_subcommand is None:
        if max_duration is None and min_duration is None:
            min_duration, max_duration = 0.5, 1.5
        elif (max_duration is not None) and (min_duration is not None):
            assert min_duration < max_duration, "min_duration >= max_duration"
        else:
            raise ValueError("min_duration and max_duration must both be set.")

        pump_calibration(min_duration, max_duration)


@click_pump_calibration.command(name="display")
@click.option("-n", "--name", type=click.STRING)
def click_display(name: str | None):
    """
    Display a graph and metadata about the current pump calibrations.
    """
    display(name)


@click_pump_calibration.command(name="change_current")
@click.argument("name", type=click.STRING)
def click_change_current(name: str):
    """
    Change the current calibration
    """
    change_current(name)


@click_pump_calibration.command(name="list")
def click_list():
    """
    Print a list of all pump calibrations done
    """
    list_()


@click_pump_calibration.command(name="publish")
@click.argument("name", type=click.STRING)
def click_publish(name: str):
    """
    Publish calibration to the leader's database.
    """
    publish_to_leader(name)


if __name__ == "__main__":
    click_pump_calibration()
