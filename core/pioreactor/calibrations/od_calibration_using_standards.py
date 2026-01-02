# -*- coding: utf-8 -*-
"""
Copyright 2023 Chris Macdonald, Pioreactor

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
from __future__ import annotations

from time import sleep
from typing import cast

import click
from click import clear
from click import confirm
from click import echo
from click import prompt
from msgspec.json import encode
from msgspec.json import format
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring as stirring
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.calibrations import utils
from pioreactor.calibrations.cli_helpers import action_block
from pioreactor.calibrations.cli_helpers import green
from pioreactor.calibrations.cli_helpers import info
from pioreactor.calibrations.cli_helpers import info_heading
from pioreactor.calibrations.cli_helpers import red
from pioreactor.config import config
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistent_storage
from pioreactor.utils import managed_lifecycle
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def introduction() -> None:
    import logging

    logging.disable(logging.WARNING)

    clear()
    info(
        """This routine will calibrate the current Pioreactor to (offline) OD600 readings using a set of standards. You'll need:
    1. A Pioreactor
    2. A set of OD600 standards in Pioreactor vials (at least 10 mL in each vial), each with a stirbar
    3. One of the standards should be a blank (no cells, only media). We'll record this last.
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
                prompt_suffix=": ",
            ).strip()

            if name == "":
                echo(red("Name cannot be empty."))
                continue
            elif name in cache:
                if confirm(green("❗️ Name already exists. Overwrite?"), prompt_suffix=": "):
                    return name
            elif name == "current":
                echo(red("Name cannot be `current`."))
                continue
            else:
                return name


def get_metadata_from_user() -> tuple[pt.PdAngle, pt.PdChannel]:
    if config.get("od_reading.config", "ir_led_intensity") == "auto":
        echo(
            red(
                "Can't use ir_led_intensity=auto with OD calibrations. Change ir_led_intensity in your config.ini to a numeric value (80 is good default). Aborting!"
            )
        )
        raise click.Abort()

    pd_channels = config["od_config.photodiode_channel"]
    ref_channel = next((k for k, v in pd_channels.items() if v == REF_keyword), None)
    if ref_channel is None:
        raise ValueError("REF required for this calibration")
    pd_channel = cast(pt.PdChannel, "1" if ref_channel == "2" else "2")

    confirm(
        green(
            f"Confirm using channel {pd_channel} with angle {config['od_config.photodiode_channel'][pd_channel]}° position in the Pioreactor?"
        ),
        abort=True,
        default=True,
        prompt_suffix=": ",
    )
    angle = cast(pt.PdAngle, config["od_config.photodiode_channel"][pd_channel])
    return angle, pd_channel


def setup_intial_instructions() -> None:
    click.clear()
    action_block(
        ["Place first standard into Pioreactor, with a stir bar. This shouldn't be the blank standard."]
    )
    while not click.confirm(green("Confirm vial is placed in Pioreactor?"), default=True, prompt_suffix=": "):
        pass


def start_stirring():
    while not confirm(green("Ready to start stirring?"), default=True, prompt_suffix=": "):
        pass

    info("Starting stirring and blocking until near target RPM...")

    st = stirring(
        target_rpm=config.getfloat("stirring.config", "initial_target_rpm"),
        unit=get_unit_name(),
        experiment=get_testing_experiment_name(),
    )
    st.block_until_rpm_is_close_to_target(abs_tolerance=120)
    return st


def choose_settings() -> float:
    config_rpm = config.getfloat("stirring", "initial_target_rpm")

    rpm = click.prompt(
        green(f"Optional: Enter RPM for stirring. [enter] for {config_rpm} RPM, default set in config.ini"),
        type=click.FloatRange(0, 10000),
        default=config_rpm,
        show_default=False,
        prompt_suffix=": ",
    )
    return rpm


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


def start_recording_standards(st: Stirrer, signal_channel):
    voltages = []
    od600_values = []

    info("Warming up OD...")

    with start_od_reading(
        config["od_config.photodiode_channel"],
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_testing_experiment_name(),
        calibration=False,
    ) as od_reader:

        def get_voltage_from_adc() -> float:
            od_readings1 = od_reader.record_from_adc()
            od_readings2 = od_reader.record_from_adc()
            assert od_readings1 is not None
            assert od_readings2 is not None
            return 0.5 * (od_readings1.ods[signal_channel].od + od_readings2.ods[signal_channel].od)

        for _ in range(3):
            # warm up
            od_reader.record_from_adc()

    while True:
        click.clear()
        standard_od = click.prompt(
            green("Enter OD600 measurement of current vial"),
            type=float,
            prompt_suffix=":",
        )
        info("Taking OD reading of current vial...")
        for i in range(4):
            click.echo(".", nl=False)
            sleep(0.5)

        click.echo(".", nl=False)
        voltage = get_voltage_from_adc()
        click.echo(".", nl=False)

        od600_values.append(standard_od)
        voltages.append(voltage)

        st.set_state(pt.JobState.SLEEPING)

        for i in range(len(od600_values)):
            click.clear()
            utils.plot_data(
                od600_values,
                voltages,
                title="OD Calibration (ongoing)",
                x_min=0,
                x_max=max(max(od600_values), 0.1),
                x_label="OD600",
                y_label="Voltage",
            )
            click.echo()

        if not click.confirm(green("Record another OD600 standard?"), default=True, prompt_suffix=": "):
            break

        action_block(
            [
                "Remove the old vial.",
                "Place the next vial. Confirm it is dry and clean.",
            ]
        )
        while not click.confirm(
            green("Confirm vial is placed in Pioreactor?"), default=True, prompt_suffix=": "
        ):
            pass
        st.set_state(pt.JobState.READY)
        info("Starting stirring...")
        st.block_until_rpm_is_close_to_target(abs_tolerance=120)
        sleep(1.0)

    click.clear()
    utils.plot_data(
        od600_values,
        voltages,
        title="OD Calibration (ongoing)",
        x_min=0,
        x_max=max(od600_values),
        x_label="OD600",
        y_label="Voltage",
    )
    action_block(["Add the media blank standard."])
    while not click.confirm(
        green("Confirm blank vial is placed in Pioreactor?"),
        default=True,
        prompt_suffix=": ",
    ):
        pass

    od600_blank = click.prompt(green("Enter OD600 of your blank"), type=float, prompt_suffix=":")
    for i in range(4):
        click.echo(".", nl=False)
        sleep(0.5)

    click.echo(".", nl=False)
    voltages.append(get_voltage_from_adc())
    click.echo(".", nl=False)

    od600_values.append(od600_blank)

    return od600_values, voltages


def run_od_calibration() -> structs.OD600Calibration:
    unit = get_unit_name()
    experiment = get_testing_experiment_name()
    curve_data_: list[float] = []
    curve_type = "poly"

    with managed_lifecycle(unit, experiment, "od_calibration"):
        introduction()
        name = get_name_from_user()

        if any(is_pio_job_running(["stirring", "od_reading"])):
            echo(red("Both stirring and OD reading should be turned off."))
            raise click.Abort()

        (
            angle,
            pd_channel,
        ) = get_metadata_from_user()
        setup_intial_instructions()

        with start_stirring() as st:
            inferred_od600s, voltages = start_recording_standards(st, pd_channel)

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

        info_heading(f"Calibration curve for `{name}`")
        info(utils.curve_to_functional_form(cal.curve_type, cal.curve_data_))
        echo()
        info_heading(f"Data for `{name}`")
        print(format(encode(cal)).decode())  # decode to go from bytes -> str
        echo()
        info(f"Finished calibration of `{name}` ✅")

        return cal
