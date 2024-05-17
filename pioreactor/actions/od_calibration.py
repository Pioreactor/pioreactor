# -*- coding: utf-8 -*-
"""
https://docs.pioreactor.com/developer-guide/adding-calibration-type
"""
from __future__ import annotations

from math import log2
from time import sleep
from typing import Callable
from typing import cast
from typing import Type

import click
from click import clear
from click import confirm
from click import echo
from click import prompt
from click import style
from msgspec.json import decode
from msgspec.json import encode
from msgspec.json import format

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring as stirring
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.config import config
from pioreactor.config import leader_address
from pioreactor.pubsub import patch_into_leader
from pioreactor.pubsub import put_into_leader
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import managed_lifecycle
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def green(string):
    return style(string, fg="green")


def bold(string):
    return style(string, bold=True)


def introduction() -> None:
    import logging

    logging.disable(logging.WARNING)

    clear()
    echo(
        """This routine will calibrate the current Pioreactor to (offline) OD600 readings. You'll need:
    1. The Pioreactor you wish to calibrate (the one you are using)
    2. At least 10mL of a culture with the highest density you'll ever observe, and its OD600 measurement
    3. A micro-pipette, or accurate tool to dispense 1ml of liquid.
    4. Accurate 10mL measurement tool (ex: graduated cylinder)
    5. Sterile media, amount to be determined shortly.
"""
    )


def get_name_from_user() -> str:
    with local_persistant_storage("od_calibrations") as cache:
        while True:
            name = prompt(
                green(
                    f"Optional: Provide a name for this calibration. [enter] to use default name `od-cal-{current_utc_datestamp()}`"
                ),
                type=str,
                default=f"od-cal-{current_utc_datestamp()}",
                show_default=False,
            ).strip()

            if name == "":
                echo("Name cannot be empty")
                continue
            elif name in cache:
                if confirm(green("❗️ Name already exists. Do you wish to overwrite?")):
                    return name
            elif name == "current":
                echo("Name cannot be `current`.")
                continue
            else:
                return name


def get_metadata_from_user() -> tuple[pt.OD600, pt.OD600, pt.mL, pt.PdAngle, pt.PdChannel]:
    if config["od_config"]["ir_led_intensity"] == "auto":
        raise ValueError(
            "Can't use auto with OD calibrations. Change ir_led_intensity in your config.ini to a numeric value (50 is good default)."
        )

    initial_od600 = prompt(
        green("Provide the OD600 measurement of your initial, high density, culture"),
        type=click.FloatRange(min=0.01, clamp=False),
    )

    minimum_od600 = prompt(
        green("Provide the minimum OD600 measurement you wish to calibrate to"),
        type=click.FloatRange(min=0, max=initial_od600, clamp=False),
    )

    while minimum_od600 >= initial_od600:
        minimum_od600 = cast(
            pt.OD600,
            prompt(
                "The minimum OD600 measurement must be less than the initial OD600 culture measurement",
                type=click.FloatRange(min=0, max=initial_od600, clamp=False),
            ),
        )

    if minimum_od600 == 0:
        minimum_od600 = 0.01

    dilution_amount = prompt(
        green("Provide the volume to be added to your vial each iteration (default = 1 mL)"),
        default=1,
        type=click.FloatRange(min=0.01, max=10, clamp=False),
    )

    number_of_points = int(log2(initial_od600 / minimum_od600) * (10 / dilution_amount))

    echo(f"This will require {number_of_points} data points.")
    echo(f"You will need at least {number_of_points * dilution_amount + 10}mL of media available.")
    confirm(green("Continue?"), abort=True, default=True)

    if "REF" not in config["od_config.photodiode_channel_reverse"]:
        raise ValueError(
            "REF required for OD calibration. Set an input to REF in [od_config.photodiode_channel] in your config."
        )
        # technically it's not required? we just need a specific PD channel to calibrate from.

    ref_channel = config["od_config.photodiode_channel_reverse"]["REF"]
    pd_channel = cast(pt.PdChannel, "1" if ref_channel == "2" else "2")

    confirm(
        green(
            f"Confirm using channel {pd_channel} with angle {config['od_config.photodiode_channel'][pd_channel]}° position in the Pioreactor"
        ),
        abort=True,
        default=True,
    )
    angle = cast(pt.PdAngle, config["od_config.photodiode_channel"][pd_channel])
    return initial_od600, minimum_od600, dilution_amount, angle, pd_channel


def setup_HDC_instructions() -> None:
    clear()
    echo(
        """ Setting up:
    1. Add 10ml of your culture to the glass vial, with a stir bar. Leave the cap off.
    2. Confirm the vial is dry and carefully place into Pioreactor.
"""
    )


def start_stirring():
    while not confirm(green("Reading to start stirring?"), default=True, abort=True):
        pass

    echo("Starting stirring and blocking until near target RPM.")

    st = stirring(
        target_rpm=config.getfloat("stirring", "target_rpm"),
        unit=get_unit_name(),
        experiment=get_testing_experiment_name(),
    )
    st.block_until_rpm_is_close_to_target(abs_tolerance=120)
    return st


def plot_data(
    x,
    y,
    title,
    x_min=None,
    x_max=None,
    interpolation_curve=None,
    highlight_recent_point=True,
):
    import plotext as plt  # type: ignore

    plt.clf()

    plt.scatter(x, y, marker="hd")

    if highlight_recent_point:
        plt.scatter([x[-1]], [y[-1]], color=204, marker="hd")

    plt.theme("pro")
    plt.title(title)
    plt.xlabel("OD600")
    plt.ylabel("OD Reading (Raw)")

    plt.plot_size(105, 22)

    if interpolation_curve:
        plt.plot(x, [interpolation_curve(x_) for x_ in x], color=204)
        plt.plot_size(145, 26)

    plt.xlim(x_min, x_max)
    plt.yfrequency(6)
    plt.xfrequency(6)

    plt.show()


def start_recording_and_diluting(
    st: Stirrer,
    initial_od600: pt.OD,
    minimum_od600: pt.OD,
    dilution_amount: float,
    pd_channel: pt.PdChannel,
) -> tuple[list[float], list[float]]:
    inferred_od600 = initial_od600
    voltages = []
    inferred_od600s = []
    current_volume_in_vial = initial_volume_in_vial = 10.0
    n_samples = int((20 - initial_volume_in_vial) / dilution_amount)

    if initial_volume_in_vial + dilution_amount * n_samples > 18:
        n_samples = n_samples - 1
        # 20mL in one vial is very scary

    total_n_samples = int(log2(initial_od600 / minimum_od600) * (initial_volume_in_vial / dilution_amount))
    count_of_samples = 0

    echo("Warming up OD...")

    with start_od_reading(
        cast(pt.PdAngleOrREF, config.get("od_config.photodiode_channel", "1")),
        cast(pt.PdAngleOrREF, config.get("od_config.photodiode_channel", "2")),
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_testing_experiment_name(),
        use_calibration=False,
    ) as od_reader:

        def get_voltage_from_adc() -> pt.Voltage:
            od_readings1 = od_reader.record_from_adc()
            od_readings2 = od_reader.record_from_adc()
            return 0.5 * (od_readings1.ods[pd_channel].od + od_readings2.ods[pd_channel].od)

        for _ in range(4):
            # warm up
            od_reader.record_from_adc()

        while inferred_od600 > minimum_od600:
            while True:
                if inferred_od600 < initial_od600 and confirm(
                    green("Do you want to enter an updated OD600 value for the current density?")
                ):
                    r = prompt(
                        green('Enter updated OD600, or "SKIP"'),
                        type=str,
                        confirmation_prompt=green("Repeat for confirmation"),
                    )
                    if r == "SKIP":
                        break

                    else:
                        try:
                            inferred_od600 = float(r)
                            break
                        except ValueError:
                            echo("OD600 entered is invalid.")
                else:
                    break

            inferred_od600s.append(inferred_od600)

            voltages.append(get_voltage_from_adc())

            for i in range(n_samples):
                clear()
                plot_data(
                    inferred_od600s,
                    voltages,
                    title="OD Calibration (ongoing)",
                    x_min=minimum_od600,
                    x_max=initial_od600,
                )
                echo()
                echo(
                    green(
                        bold(
                            f"Test {count_of_samples+1} of {total_n_samples} [{'#' * (count_of_samples+1) }{' ' * (total_n_samples - count_of_samples - 1)}]"
                        )
                    )
                )
                echo(f"Add {dilution_amount}ml of media to vial.")

                while not confirm(green("Continue?"), default=False):
                    pass

                current_volume_in_vial = current_volume_in_vial + dilution_amount

                for _ in range(4):
                    echo(".", nl=False)
                    sleep(0.5)

                echo(".", nl=False)
                voltages.append(get_voltage_from_adc())
                echo(".", nl=False)

                inferred_od600 = (
                    inferred_od600 * (current_volume_in_vial - dilution_amount) / current_volume_in_vial
                )
                inferred_od600s.append(inferred_od600)

                if inferred_od600 <= minimum_od600:
                    break

                count_of_samples += 1

            else:
                # executed if the loop did not break
                clear()
                plot_data(
                    inferred_od600s,
                    voltages,
                    title="OD Calibration (ongoing)",
                    x_min=minimum_od600,
                    x_max=initial_od600,
                )
                st.set_state("sleeping")
                echo()
                echo(style("Stop❗", fg="red"))
                echo("Carefully remove vial.")
                echo("(Optional: take new OD600 reading with external instrument.)")
                echo(
                    f"Reduce volume in vial by {n_samples*dilution_amount}mL. There should be 10mL remaining in your vial."
                )
                echo("Confirm vial outside is dry and clean. Place back into Pioreactor.")
                while not confirm(green("Continue?"), default=False):
                    pass
                current_volume_in_vial = initial_volume_in_vial
                st.set_state("ready")
                st.block_until_rpm_is_close_to_target(abs_tolerance=120)
                sleep(1.0)

        clear()
        plot_data(
            inferred_od600s,
            voltages,
            title="OD Calibration (ongoing)",
            x_min=minimum_od600,
            x_max=initial_od600,
        )
        echo("Empty the vial and replace with 10 mL of the media you used.")
        od600_of_blank = prompt(
            green("What is the OD600 of your blank?"),
            type=float,
            confirmation_prompt=green("Repeat for confirmation"),
        )
        echo("Confirm vial outside is dry and clean. Place back into Pioreactor.")
        while not confirm(green("Continue?"), default=False):
            pass
        echo("Reading blank...")

        value = get_voltage_from_adc()
        for i in range(5):
            if value > min(voltages):
                echo("Reading is too high, trying again...")
                value = get_voltage_from_adc()
            else:
                break
        else:
            raise ValueError(f"Why is the blank reading, {value}V, higher than everything else: {voltages}V?")

        voltages.append(value)
        inferred_od600s.append(od600_of_blank)

        return inferred_od600s, voltages


def calculate_curve_of_best_fit(
    voltages: list[pt.Voltage], inferred_od600s: list[pt.OD], degree: int
) -> tuple[list[float], str]:
    import numpy as np

    # weigh the last point, the "blank measurement", more.
    # 1. It's far away from the other points
    # 2. We have prior knowledge that OD~0 when V~0.
    n = len(voltages)
    weights = np.ones_like(voltages)
    weights[-1] = n / 2

    try:
        coefs = np.polyfit(inferred_od600s, voltages, deg=degree, w=weights).tolist()
    except Exception:
        echo("Unable to fit.")
        coefs = np.zeros(degree).tolist()

    return coefs, "poly"


def show_results_and_confirm_with_user(
    curve_data: list[float],
    curve_type: str,
    voltages: list[pt.Voltage],
    inferred_od600s: list[pt.OD],
) -> tuple[bool, int]:
    clear()

    curve_callable = curve_to_callable(curve_type, curve_data)

    plot_data(
        inferred_od600s,
        voltages,
        title="OD Calibration with curve of best fit",
        interpolation_curve=curve_callable,
        highlight_recent_point=False,
    )
    echo()
    echo(f"Calibration curve: {curve_to_functional_form(curve_type, curve_data)}")
    r = prompt(
        green(
            f"""
y: confirm and save to disk
n: abort completely
d: choose a new degree for polynomial fit (currently {len(curve_data)-1})

"""
        ),
        type=click.Choice(["y", "n", "d"]),
    )
    if r == "y":
        return True, -1
    elif r == "n":
        raise click.Abort()
    elif r == "d":
        d = prompt(green("Enter new degree"), type=click.IntRange(1, 5, clamp=True))
        return False, d
    else:
        raise click.Abort()


def save_results(
    curve_data_: list[float],
    curve_type: str,
    voltages: list[pt.Voltage],
    od600s: list[pt.OD],
    angle,
    name: str,
    pd_channel: pt.PdChannel,
    unit: str,
) -> structs.ODCalibration:
    if angle == "45":
        struct: Type[structs.ODCalibration] = structs.OD45Calibration
    elif angle == "90":
        struct = structs.OD90Calibration
    elif angle == "135":
        struct = structs.OD135Calibration
    elif angle == "180":
        struct = structs.OD180Calibration
    else:
        raise ValueError()

    data_blob = struct(
        created_at=current_utc_datetime(),
        pioreactor_unit=unit,
        name=name,
        angle=angle,
        maximum_od600=max(od600s),
        minimum_od600=min(od600s),
        minimum_voltage=min(voltages),
        maximum_voltage=max(voltages),
        curve_data_=curve_data_,
        curve_type=curve_type,
        voltages=voltages,
        od600s=od600s,
        ir_led_intensity=float(config["od_config"]["ir_led_intensity"]),
        pd_channel=pd_channel,
    )

    with local_persistant_storage("od_calibrations") as cache:
        cache[name] = encode(data_blob)

    publish_to_leader(name)
    change_current(name)

    return data_blob


def get_data_from_data_file(data_file: str) -> tuple[pt.PdChannel, pt.PdAngle, list[float], list[float]]:
    import json

    click.echo(f"Pulling data from {data_file}...")

    with open(data_file, "r") as f:
        data = json.loads(f.read())

    ods, voltages = data["od600s"], data["voltages"]
    assert len(ods) == len(voltages), "data must be the same length."

    pd_channel = data.get(
        "pd_channel",
        "1" if config["od_config.photodiode_channel_reverse"]["REF"] == "2" else "2",
    )
    angle = data.get("angle", str(config["od_config.photodiode_channel"][pd_channel]))

    return pd_channel, angle, ods, voltages


def od_calibration(data_file: str | None) -> None:
    unit = get_unit_name()
    experiment = get_testing_experiment_name()

    if any(is_pio_job_running(["stirring", "od_reading"])):
        raise ValueError("Stirring and OD reading should be turned off.")

    with managed_lifecycle(unit, experiment, "od_calibration"):
        introduction()
        name = get_name_from_user()

        if data_file is None:
            (
                initial_od600,
                minimum_od600,
                dilution_amount,
                angle,
                pd_channel,
            ) = get_metadata_from_user()
            setup_HDC_instructions()

            with start_stirring() as st:
                inferred_od600s, voltages = start_recording_and_diluting(
                    st, initial_od600, minimum_od600, dilution_amount, pd_channel
                )
        else:
            pd_channel, angle, inferred_od600s, voltages = get_data_from_data_file(data_file)

        degree = 5 if len(voltages) > 10 else 3
        while True:
            curve_data_, curve_type = calculate_curve_of_best_fit(voltages, inferred_od600s, degree)
            okay_with_result, degree = show_results_and_confirm_with_user(
                curve_data_, curve_type, voltages, inferred_od600s
            )
            if okay_with_result:
                break

        echo("Saving results...")
        data_blob = save_results(
            curve_data_,
            curve_type,
            voltages,
            inferred_od600s,
            angle,
            name,
            pd_channel,
            unit,
        )
        echo(style(f"Calibration curve for `{name}`", underline=True, bold=True))
        echo(curve_to_functional_form(curve_type, curve_data_))
        echo()
        echo(style(f"Data for `{name}`", underline=True, bold=True))
        print(format(encode(data_blob)).decode())
        echo()
        echo(f"Finished calibration of `{name}` ✅")

        if not config.getboolean("od_config", "use_calibration", fallback=False):
            echo()
            echo(
                bold(
                    "Currently [od_config][use_calibration] is set to 0 in your config.ini. This should be set to 1 to use calibrations.",
                )
            )
        return


def curve_to_functional_form(curve_type: str, curve_data) -> str:
    if curve_type == "poly":
        d = len(curve_data)
        return " + ".join(
            [(f"{c:0.3f}x^{d - i - 1}" if (i < d - 1) else f"{c:0.3f}") for i, c in enumerate(curve_data)]
        )
    else:
        raise ValueError()


def curve_to_callable(curve_type: str, curve_data) -> Callable:
    if curve_type == "poly":
        import numpy as np

        def curve_callable(x):
            return np.polyval(curve_data, x)

        return curve_callable

    else:
        raise NotImplementedError


def display(name: str | None) -> None:
    def display_from_calibration_blob(data_blob: dict) -> None:
        voltages = data_blob["voltages"]
        ods = data_blob["od600s"]
        name, angle = data_blob["name"], data_blob["angle"]
        echo()
        echo(style(f"Calibration `{name}`", underline=True, bold=True))
        plot_data(
            ods,
            voltages,
            title=f"`{name}`, calibration of {angle}°",
            highlight_recent_point=False,
            interpolation_curve=curve_to_callable(data_blob["curve_type"], data_blob["curve_data_"]),
        )
        echo()
        echo(style(f"Calibration curve for `{name}`", underline=True, bold=True))
        echo(curve_to_functional_form(data_blob["curve_type"], data_blob["curve_data_"]))
        echo()
        echo(style(f"Data for `{name}`", underline=True, bold=True))
        print(format(encode(data_blob)).decode())

    if name is not None:
        with local_persistant_storage("od_calibrations") as c:
            display_from_calibration_blob(decode(c[name]))
    else:
        with local_persistant_storage("current_od_calibration") as c:
            for angle in c.iterkeys():
                display_from_calibration_blob(decode(c[angle]))
                echo()
                echo()
                echo()


def publish_to_leader(name: str) -> bool:
    success = True

    with local_persistant_storage("od_calibrations") as all_calibrations:
        calibration_result = decode(
            all_calibrations[name], type=structs.subclass_union(structs.ODCalibration)
        )

    try:
        res = put_into_leader("/api/calibrations", json=calibration_result)
        if not res.ok:
            success = False
    except Exception as e:
        print(e)
        success = False
    if not success:
        echo(f"Could not update in database on leader at http://{leader_address}/api/calibrations ❌")
    return success


def change_current(name: str) -> None:
    try:
        with local_persistant_storage("od_calibrations") as all_calibrations:
            new_calibration = decode(
                all_calibrations[name],
                type=structs.subclass_union(structs.ODCalibration),
            )

        angle = new_calibration.angle
        with local_persistant_storage("current_od_calibration") as current_calibrations:
            if angle in current_calibrations:
                old_calibration = decode(
                    current_calibrations[angle],
                    type=structs.subclass_union(structs.ODCalibration),
                )
            else:
                old_calibration = None

            current_calibrations[angle] = encode(new_calibration)

        try:
            res = patch_into_leader(
                f"/api/calibrations/{get_unit_name()}/{new_calibration.type}/{new_calibration.name}",
                json={"current": 1},
            )
            if not res.ok:
                raise Exception
        except Exception:
            echo("Could not update in database on leader ❌")

        if old_calibration:
            echo(f"Replaced `{old_calibration.name}` with `{new_calibration.name}`   ✅")
        else:
            echo(f"Set `{new_calibration.name}` to current calibration  ✅")
        echo()

    except Exception:
        echo("Failed to swap.")
        raise click.Abort()


def list_() -> None:
    # get current calibrations
    current = []
    with local_persistant_storage("current_od_calibration") as c:
        for _ in c.iterkeys():
            cal = decode(c[_], type=structs.subclass_union(structs.ODCalibration))
            current.append(cal.name)

    echo(bold(f"{'Name':18s} {'Date':18s} {'Angle':12s} {'Currently in use?':20s}"))
    with local_persistant_storage("od_calibrations") as c:
        for name in c.iterkeys():
            try:
                cal = decode(c[name], type=structs.subclass_union(structs.ODCalibration))
                echo(
                    f"{cal.name:18s} {cal.created_at:%d %b, %Y}       {cal.angle:12s} {'✅' if cal.name in current else ''}",
                )
            except Exception:
                pass


@click.group(invoke_without_command=True, name="od_calibration")
@click.option(
    "-f", "--json-file", type=click.Path(exists=True, dir_okay=False, readable=True, resolve_path=True)
)
@click.pass_context
def click_od_calibration(ctx, json_file: str | None) -> None:
    """
    Calibrate OD600 to voltages

    To load in data from a json file, the necessary fields are "od600s" and "voltages", optional: "pd_channel" and "angle"
    Ex:

    {
        "od600s": [1.0, 0.5, 0.25, 0],
        "voltages":[0.5, 0.25, 0.125, 0.0]
    }

    """
    if ctx.invoked_subcommand is None:
        od_calibration(json_file)


@click_od_calibration.command(name="display")
@click.option("-n", "--name", type=click.STRING, help="default is current")
def click_display(name: str) -> None:
    display(name)


@click_od_calibration.command(name="change_current")
@click.argument("name", type=click.STRING)
def click_change_current(name: str) -> None:
    change_current(name)


@click_od_calibration.command(name="list")
def click_list() -> None:
    list_()
