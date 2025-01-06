# -*- coding: utf-8 -*-
"""
https://docs.pioreactor.com/developer-guide/adding-calibration-type

This should have used calibration_type as the keys, but instead it uses media, alt_media, and waste..
"""
from __future__ import annotations

import time
from typing import Callable
from typing import Literal

import click
from click import Abort
from click import clear
from click import confirm
from click import echo
from click import prompt
from click import style
from msgspec.json import encode
from msgspec.json import format

from pioreactor import structs
from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import remove_waste
from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.config import config
from pioreactor.hardware import voltage_in_aux
from pioreactor.logging import create_logger
from pioreactor.types import PumpCalibrationDevices
from pioreactor.utils import managed_lifecycle
from pioreactor.utils.math_helpers import correlation
from pioreactor.utils.math_helpers import simple_linear_regression_with_forced_nil_intercept
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name


def green(string: str) -> str:
    return style(string, fg="green")


def red(string: str) -> str:
    return style(string, fg="red")


def bold(string: str) -> str:
    return style(string, bold=True)


def introduction(pump_device) -> None:
    import logging

    logging.disable(logging.WARNING)

    echo(
        f"""This routine will calibrate the {pump_device} on your current Pioreactor. You'll need:

    1. A Pioreactor
    2. A vial placed on a scale with accuracy at least 0.1g
       OR an accurate graduated cylinder.
    3. A larger container filled with water
    4. {pump_device} connected to the correct PWM channel (1, 2, 3, or 4) as determined in your configuration.

We will dose for a set duration, you'll measure how much volume was expelled, and then record it back here. After doing this a few times, we can construct a calibration line for this pump.
"""
    )
    confirm(green("Proceed?"), abort=True, default=True)
    clear()
    echo(
        "You don't need to place your vial in your Pioreactor. While performing this calibration, keep liquids away from the Pioreactor to keep it safe & dry"
    )
    confirm(green("Proceed?"), abort=True, default=True)
    clear()


def get_metadata_from_user(pump_device: PumpCalibrationDevices) -> str:
    existing_calibrations = list_of_calibrations_by_device(pump_device)
    while True:
        name = prompt(
            style(
                f"Optional: Provide a name for this {pump_device} calibration. [enter] to use default name `{pump_device}-{current_utc_datestamp()}`",
                fg="green",
            ),
            type=str,
            default=f"{pump_device}-{current_utc_datestamp()}",
            show_default=False,
        ).strip()
        if name == "":
            echo("Name cannot be empty")
            continue
        elif name in existing_calibrations:
            if confirm(green("❗️ Name already exists. Do you wish to overwrite?")):
                break
        else:
            break
    return name


def setup(
    pump_device: PumpCalibrationDevices, execute_pump: Callable, hz: float, dc: float, unit: str
) -> None:
    # set up...
    try:
        channel_pump_is_configured_for = config.get("PWM_reverse", pump_device.removesuffix("_pump"))
    except KeyError:
        echo(
            red(
                f"❌ {pump_device} is not present in config.ini. Please add it to the [PWM] section and try again."
            )
        )
        raise Abort()
    clear()
    echo()
    echo(green(bold("Step 2")))
    echo("We need to prime the pump by filling the tubes completely with water.")
    echo(
        "1. From your Pioreactor vial, remove one of the female luer locks. Attach it to the end of the *sink tube*."
    )
    echo("2. Fill a container with water.")
    echo("3. Submerge both ends of the pump's tubes into the water.")
    echo(
        "Make sure the pump's power is connected to " + bold(f"PWM channel {channel_pump_is_configured_for}.")
    )
    echo(
        "Run the pumps continuously until the tubes are completely filled with water and there are no air pockets in the tubes."
    )
    echo()

    while not confirm(green("Ready to start pumping?")):
        pass

    echo(
        bold(
            "Press CTRL+C when the tubes are completely filled with water and there are no air pockets in the tubes."
        )
    )

    try:
        execute_pump(
            continuously=True,
            source_of_event="pump_calibration",
            unit=get_unit_name(),
            experiment=get_testing_experiment_name(),
            calibration=structs.SimplePeristalticPumpCalibration(
                calibration_name="calibration",
                created_at=current_utc_datetime(),
                curve_type="poly",
                curve_data_=[1, 0],
                hz=hz,
                dc=dc,
                voltage=voltage_in_aux(),
                calibrated_on_pioreactor_unit=unit,
                recorded_data={"x": [], "y": []},
            ),
        )
    except KeyboardInterrupt:
        pass

    echo()

    time.sleep(0.5)  # pure UX
    return


def choose_settings() -> tuple[float, float]:
    hz = prompt(
        style(green("Optional: Enter frequency of PWM. [enter] for default 250 hz")),
        type=click.FloatRange(0.1, 10000),
        default=250,
        show_default=False,
    )
    dc = prompt(
        green(
            "Optional: Enter duty cycle percent as a whole number. [enter] for default 100%",
        ),
        type=click.IntRange(0, 100),
        default=100,
        show_default=False,
    )

    return hz, dc


def plot_data(x, y, title, x_min=None, x_max=None, interpolation_curve=None, highlight_recent_point=True):
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
    plt.xlabel("Duration")
    plt.ylabel("Volume")
    plt.xlim(x_min, x_max)
    plt.yfrequency(6)
    plt.xfrequency(6)

    plt.show()


def run_tests(
    execute_pump: Callable,
    hz: float,
    dc: float,
    min_duration: float,
    max_duration: float,
    pump_device: PumpCalibrationDevices,
    unit: str,
) -> tuple[list[float], list[float]]:
    clear()
    echo()
    echo(green(bold("Step 3")))
    echo("Beginning tests.")

    empty_calibration = structs.SimplePeristalticPumpCalibration(
        calibration_name="_test",
        curve_data_=[1, 0],
        curve_type="poly",
        hz=hz,
        dc=dc,
        created_at=current_utc_datetime(),
        voltage=voltage_in_aux(),
        calibrated_on_pioreactor_unit=unit,
        recorded_data={"x": [], "y": []},
    )

    results: list[float] = []
    durations_to_test = [min_duration] * 4 + [(min_duration + max_duration) / 2] * 2 + [max_duration] * 4
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
                echo()
                echo("Remove the water from the measuring container or tare your weighing scale.")

            echo(
                "We will run the pump for a set amount of time, and you will measure how much liquid is expelled."
            )
            echo("Use a small container placed on top of an accurate weighing scale.")
            echo("Hold the end of the outflow tube above so the container catches the expelled liquid.")
            echo()
            echo(
                green(
                    bold(
                        f"Test {i+1} of {n_samples} [{'#' * (i+1) }{' ' * (n_samples - i - 1)}]",
                    )
                )
            )
            while not confirm(style(green(f"Ready to test {duration:.2f}s?"))):
                pass

            execute_pump(
                duration=duration,
                source_of_event="pump_calibration",
                unit=get_unit_name(),
                experiment=get_testing_experiment_name(),
                calibration=empty_calibration,
            )

            r = prompt(
                style(green("Enter amount of water expelled (g or ml), or REDO")),
                confirmation_prompt=style(green("Repeat for confirmation")),
            )
            if r == "REDO":
                clear()
                echo()
                continue

            try:
                results.append(float(r))
                clear()
                echo()
                break
            except ValueError:
                echo(red("Not a number - retrying."))

    return durations_to_test, results


def save_results(
    name: str,
    pump_device: Literal["media_pump", "waste_pump", "alt_media_pump"],
    duration_: float,
    bias_: float,
    hz: float,
    dc: float,
    voltage: float,
    durations: list[float],
    volumes: list[float],
    unit: str,
) -> structs.SimplePeristalticPumpCalibration:
    pump_calibration_result = structs.SimplePeristalticPumpCalibration(
        calibration_name=name,
        calibrated_on_pioreactor_unit=unit,
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=[duration_, bias_],
        hz=hz,
        dc=dc,
        voltage=voltage_in_aux(),
        recorded_data={"x": durations, "y": volumes},
    )

    return pump_calibration_result


def run_pump_calibration(
    pump_device, min_duration: float = 0.40, max_duration: float = 1.5
) -> structs.SimplePeristalticPumpCalibration:
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    logger = create_logger("pump_calibration", unit=unit, experiment=experiment)
    logger.info("Starting pump calibration.")

    with managed_lifecycle(unit, experiment, "pump_calibration"):
        clear()
        introduction(pump_device)

        if pump_device == "media_pump":
            execute_pump = add_media
        elif pump_device == "alt_media_pump":
            execute_pump = add_alt_media
        elif pump_device == "waste_pump":
            execute_pump = remove_waste
        else:
            raise ValueError()

        name = get_metadata_from_user(pump_device)

        is_ready = True
        while is_ready:
            hz, dc = choose_settings()
            setup(pump_device, execute_pump, hz, dc, unit)

            is_ready = confirm(
                style(green("Do you want to change the frequency or duty cycle?")),
                prompt_suffix=" ",
                default=False,
            )

        durations, volumes = run_tests(execute_pump, hz, dc, min_duration, max_duration, pump_device, unit)

        (slope, std_slope), (
            bias,
            std_bias,
        ) = simple_linear_regression_with_forced_nil_intercept(durations, volumes)

        plot_data(
            durations,
            volumes,
            title="Pump Calibration",
            x_min=min(durations),
            x_max=max(durations),
            interpolation_curve=curve_to_callable("poly", [slope, bias]),
            highlight_recent_point=False,
        )

        data_blob = save_results(
            name=name,
            pump_device=pump_device,
            duration_=slope,
            bias_=bias,
            hz=hz,
            dc=dc,
            voltage=voltage_in_aux(),
            durations=durations,
            volumes=volumes,
            unit=unit,
        )
        echo()
        echo(style(f"Linear calibration curve for `{name}`", underline=True, bold=True))
        echo()
        echo(f"slope={slope:0.3f} ± {std_slope:0.3f}, bias={bias:0.3f} ± {std_bias:0.3f}")
        echo()
        echo(style(f"Data for `{name}`", underline=True, bold=True))
        print(format(encode(data_blob)).decode())
        echo()

        echo(
            f"Calibration is best for volumes between {(slope * min_duration + bias):0.2f}mL to {(slope * max_duration + bias):0.2f}mL, but will be okay for outside this range too."
        )

        # check parameters for problems
        if correlation(durations, volumes) < 0:
            logger.warning("Correlation is negative - you probably want to rerun this calibration...")
        if std_slope > 0.04:
            logger.warning("Too much uncertainty in slope - you probably want to rerun this calibration...")

        echo(f"Finished {pump_device} calibration `{name}`.")
        return data_blob
