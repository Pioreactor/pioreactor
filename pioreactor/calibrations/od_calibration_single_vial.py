# -*- coding: utf-8 -*-
"""
https://docs.pioreactor.com/developer-guide/adding-calibration-type
"""
from __future__ import annotations

from math import log2
from time import sleep
from typing import cast

import click
from click import clear
from click import confirm
from click import echo
from click import prompt
from click import style
from msgspec.json import encode
from msgspec.json import format

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring as stirring
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.calibrations import utils
from pioreactor.config import config
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistent_storage
from pioreactor.utils import managed_lifecycle
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def green(string: str) -> str:
    return style(string, fg="green")


def red(string: str) -> str:
    return style(string, fg="red")


def bold(string: str) -> str:
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
    with local_persistent_storage("od_calibrations") as cache:
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


def get_metadata_from_user() -> tuple[pt.CalibratedOD, pt.CalibratedOD, pt.mL, pt.PdAngle, pt.PdChannel]:
    if config.get("od_reading.config", "ir_led_intensity") == "auto":
        echo(
            red(
                "Can't use ir_led_intensity=auto with OD calibrations. Change ir_led_intensity in your config.ini to a numeric value (70 is good default). Aborting!"
            )
        )
        raise click.Abort()

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
            pt.CalibratedOD,
            prompt(
                "The minimum OD600 measurement must be less than the initial OD600 culture measurement",
                type=click.FloatRange(min=0, max=initial_od600, clamp=False),
            ),
        )

    if minimum_od600 == 0:
        minimum_od600 = 0.01

    dilution_amount = prompt(
        green("Provide the volume to be added to your vial each iteration (default = 2 mL)"),
        default=2,
        type=click.FloatRange(min=0.01, max=10, clamp=False),
    )

    number_of_points = int(log2(initial_od600 / minimum_od600) * (10 / dilution_amount)) + 1

    echo(f"This will require {number_of_points} data points.")
    echo(f"You will need at least {number_of_points * dilution_amount + 10}mL of media available.")
    confirm(green("Continue?"), abort=True, default=True)

    if "REF" not in config["od_config.photodiode_channel_reverse"]:
        echo(
            red(
                "REF required for OD calibration. Set an input to REF in [od_config.photodiode_channel] in your config."
            )
        )
        raise click.Abort()
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
        target_rpm=config.getfloat("stirring.config", "target_rpm"),
        unit=get_unit_name(),
        experiment=get_testing_experiment_name(),
    )
    st.block_until_rpm_is_close_to_target(abs_tolerance=120)
    return st


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
        # n_samples is the num samples to run before risk of overflow

    total_n_samples = (
        int(log2(initial_od600 / minimum_od600) * (initial_volume_in_vial / dilution_amount)) + 1
    )
    count_of_samples = 0

    echo("Warming up OD...")

    with start_od_reading(
        cast(pt.PdAngleOrREF, config.get("od_config.photodiode_channel", "1")),
        cast(pt.PdAngleOrREF, config.get("od_config.photodiode_channel", "2")),
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_testing_experiment_name(),
        calibration=False,
    ) as od_reader:

        def get_voltage_from_adc() -> pt.Voltage:
            od_readings1 = od_reader.record_from_adc()
            od_readings2 = od_reader.record_from_adc()
            assert od_readings1 is not None
            assert od_readings2 is not None
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
                utils.plot_data(
                    inferred_od600s,
                    voltages,
                    title="OD Calibration (ongoing)",
                    x_label="OD600",
                    y_label="Voltage",
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
                utils.plot_data(
                    inferred_od600s,
                    voltages,
                    title="OD Calibration (ongoing)",
                    x_label="OD600",
                    y_label="Voltage",
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
        utils.plot_data(
            inferred_od600s,
            voltages,
            title="OD Calibration (ongoing)",
            x_label="OD600",
            y_label="Voltage",
            x_min=minimum_od600,
            x_max=initial_od600,
        )
        echo("Empty the vial and replace with 10 mL of the media you used.")
        while True:
            od600_of_blank = prompt(
                green("What is the OD600 of your blank?"),
                type=str,
                confirmation_prompt=green("Repeat for confirmation"),
            )
            try:
                od600_of_blank = float(od600_of_blank)
                break
            except ValueError:
                echo("OD600 entered is invalid.")

        echo("Confirm vial outside is dry and clean. Place back into Pioreactor.")
        while not confirm(green("Continue?"), default=False):
            pass
        echo("Reading blank...")

        value = get_voltage_from_adc()
        voltages.append(value)
        inferred_od600s.append(od600_of_blank)

        return inferred_od600s, voltages


def to_struct(
    curve_data_: list[float],
    curve_type: str,
    voltages: list[pt.Voltage],
    od600s: list[pt.OD],
    angle,
    name: str,
    pd_channel: pt.PdChannel,
    unit: str,
) -> structs.OD600Calibration:
    data_blob = structs.OD600Calibration(
        created_at=current_utc_datetime(),
        calibrated_on_pioreactor_unit=unit,
        calibration_name=name,
        angle=angle,
        curve_data_=curve_data_,
        curve_type=curve_type,
        recorded_data={"x": od600s, "y": voltages},
        ir_led_intensity=float(config["od_reading.config"]["ir_led_intensity"]),
        pd_channel=pd_channel,
    )

    return data_blob


def run_od_calibration() -> structs.OD600Calibration:
    unit = get_unit_name()
    experiment = get_testing_experiment_name()
    curve_data_: list[float] = []
    curve_type = "poly"

    with managed_lifecycle(unit, experiment, "od_calibration"):
        introduction()
        name = get_name_from_user()

        if any(is_pio_job_running(["stirring", "od_reading"])):
            echo(red("Both Stirring and OD reading should be turned off."))
            raise click.Abort()

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

        cal = to_struct(
            curve_data_,
            curve_type,
            voltages,
            inferred_od600s,
            angle,
            name,
            pd_channel,
            unit,
        )

        n = len(voltages)
        weights = [1.0] * n
        weights[0] = n / 2

        while not cal.curve_data_:
            cal = utils.crunch_data_and_confirm_with_user(cal, initial_degree=3, weights=weights)

        echo(style(f"Calibration curve for `{name}`", underline=True, bold=True))
        echo(utils.curve_to_functional_form(cal.curve_type, cal.curve_data_))
        echo()
        echo(style(f"Data for `{name}`", underline=True, bold=True))
        print(format(encode(cal)).decode())
        echo()
        echo(f"Finished calibration of `{name}` ✅")

        return cal
