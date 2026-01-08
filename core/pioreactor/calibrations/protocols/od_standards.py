# -*- coding: utf-8 -*-
"""
Copyright 2023 Chris Macdonald, Pioreactor

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
from __future__ import annotations

import uuid
from time import sleep
from typing import cast

import click
from click import clear
from click import confirm
from click import echo
from click import prompt
from msgspec import to_builtins
from msgspec.json import encode
from msgspec.json import format
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import average_over_od_readings
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring as stirring
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations import utils
from pioreactor.calibrations.cli_helpers import action_block
from pioreactor.calibrations.cli_helpers import green
from pioreactor.calibrations.cli_helpers import info
from pioreactor.calibrations.cli_helpers import info_heading
from pioreactor.calibrations.cli_helpers import red
from pioreactor.calibrations.registry import CalibrationProtocol
from pioreactor.calibrations.session_flow import fields
from pioreactor.calibrations.session_flow import run_session_in_cli
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionEngine
from pioreactor.calibrations.session_flow import SessionExecutor
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import utc_iso_timestamp
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


def get_metadata_from_user(target_device: pt.ODCalibrationDevices) -> dict[pt.PdChannel, pt.PdAngle]:
    if config.get("od_reading.config", "ir_led_intensity") == "auto":
        echo(
            red(
                "Can't use ir_led_intensity=auto with OD calibrations. Change ir_led_intensity in your config.ini to a numeric value (80 is good default). Aborting!"
            )
        )
        raise click.Abort()

    pd_channels = config["od_config.photodiode_channel"]
    ref_channels = [k for k, v in pd_channels.items() if v == REF_keyword]
    if not ref_channels:
        raise ValueError("REF required for this calibration")

    channel_angle_map: dict[pt.PdChannel, pt.PdAngle] = {}
    for channel, angle in pd_channels.items():
        if angle in (None, "", REF_keyword):
            continue
        channel_angle_map[cast(pt.PdChannel, channel)] = cast(pt.PdAngle, angle)

    if not channel_angle_map:
        raise ValueError("Need at least one non-REF PD channel for this calibration")

    if target_device != "od":
        target_angle = target_device.removeprefix("od")
        channel_angle_map = {
            channel: angle for channel, angle in channel_angle_map.items() if angle == target_angle
        }
        if not channel_angle_map:
            echo(
                red(
                    f"No channels configured for angle {target_angle}°. Check [od_config.photodiode_channel]."
                )
            )
            raise click.Abort()

    channel_summary = ", ".join(
        f"{channel}={angle}°"
        for channel, angle in sorted(channel_angle_map.items(), key=lambda item: int(item[0]))
    )
    confirm(
        green(f"Confirm using channels {channel_summary} in the Pioreactor?"),
        abort=True,
        default=True,
        prompt_suffix=": ",
    )
    return channel_angle_map


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
    config_rpm = config.getfloat("stirring.config", "initial_target_rpm")

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


def start_recording_standards(
    st: Stirrer, channel_angle_map: dict[pt.PdChannel, pt.PdAngle]
) -> tuple[list[pt.OD], dict[pt.PdChannel, list[pt.Voltage]]]:
    voltages_by_channel: dict[pt.PdChannel, list[float]] = {channel: [] for channel in channel_angle_map}
    od600_values = []
    signal_channels = sorted(channel_angle_map.keys(), key=int)

    info("Warming up OD...")

    with start_od_reading(
        config["od_config.photodiode_channel"],
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_testing_experiment_name(),
        calibration=False,
    ) as od_reader:

        def get_voltages_from_adc() -> dict[pt.PdChannel, pt.Voltage]:
            od_readings1 = od_reader.record_from_adc()
            od_readings2 = od_reader.record_from_adc()
            od_readings3 = od_reader.record_from_adc()
            assert od_readings1 is not None
            assert od_readings2 is not None
            assert od_readings3 is not None
            averaged_readings = average_over_od_readings(od_readings1, od_readings2, od_readings3)
            return {channel: averaged_readings.ods[channel].od for channel in signal_channels}

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
        voltages = get_voltages_from_adc()
        click.echo(".", nl=False)

        od600_values.append(standard_od)
        for channel, voltage in voltages.items():
            voltages_by_channel[channel].append(voltage)

        st.set_state(pt.JobState.SLEEPING)

        for channel in signal_channels:
            click.clear()
            utils.plot_data(
                od600_values,
                voltages_by_channel[channel],
                title=f"OD Calibration (ongoing) - channel {channel} ({channel_angle_map[channel]}°)",
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

    for channel in signal_channels:
        click.clear()
        utils.plot_data(
            od600_values,
            voltages_by_channel[channel],
            title=f"OD Calibration (ongoing) - channel {channel} ({channel_angle_map[channel]}°)",
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

    st.set_state(pt.JobState.READY)
    info("Starting stirring...")
    st.block_until_rpm_is_close_to_target(abs_tolerance=120)
    sleep(1.0)
    od600_blank = click.prompt(green("Enter OD600 of your blank"), type=float, prompt_suffix=":")
    for i in range(4):
        click.echo(".", nl=False)
        sleep(0.5)

    click.echo(".", nl=False)
    blank_voltages = get_voltages_from_adc()
    click.echo(".", nl=False)

    od600_values.append(od600_blank)

    for channel, voltage in blank_voltages.items():
        voltages_by_channel[channel].append(voltage)

    return od600_values, voltages_by_channel


def run_od_calibration(target_device: pt.ODCalibrationDevices) -> list[structs.OD600Calibration]:
    unit = get_unit_name()
    experiment = get_testing_experiment_name()
    curve_type = "poly"
    calibrations: list[structs.OD600Calibration] = []

    with managed_lifecycle(unit, experiment, "od_calibration"):
        introduction()
        name = get_name_from_user()

        if any(is_pio_job_running(["stirring", "od_reading"])):
            echo(red("Both stirring and OD reading should be turned off."))
            raise click.Abort()

        channel_angle_map = get_metadata_from_user(target_device)
        setup_intial_instructions()

        with start_stirring() as st:
            inferred_od600s, voltages_by_channel = start_recording_standards(st, channel_angle_map)

        for pd_channel, angle in sorted(channel_angle_map.items(), key=lambda item: int(item[0])):
            curve_data_: list[float] = []
            voltages = voltages_by_channel[pd_channel]
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

            info_heading(f"Calibration curve for `{name}` (channel {pd_channel}, {angle}°)")
            info(utils.curve_to_functional_form(cal.curve_type, cal.curve_data_))
            echo()
            info_heading(f"Data for `{name}` (channel {pd_channel}, {angle}°)")
            print(format(encode(cal)).decode())  # decode to go from bytes -> str
            echo()
            info(f"Finished calibration of `{name}` for channel {pd_channel} ✅")
            calibrations.append(cal)

        return calibrations


def _channel_angle_map_from_config(
    target_device: pt.ODCalibrationDevices,
) -> tuple[dict[pt.PdChannel, pt.PdAngle], str]:
    pd_channels = config["od_config.photodiode_channel"]
    ref_channels = [k for k, v in pd_channels.items() if v == REF_keyword]
    if not ref_channels:
        raise ValueError("REF required for this calibration")

    channel_angle_map: dict[pt.PdChannel, pt.PdAngle] = {}
    for channel, angle in pd_channels.items():
        if angle in (None, "", REF_keyword):
            continue
        channel_angle_map[cast(pt.PdChannel, channel)] = cast(pt.PdAngle, angle)

    if not channel_angle_map:
        raise ValueError("Need at least one non-REF PD channel for this calibration")

    if target_device != "od":
        target_angle = target_device.removeprefix("od")
        channel_angle_map = {
            channel: angle for channel, angle in channel_angle_map.items() if angle == target_angle
        }
        if not channel_angle_map:
            raise ValueError(
                f"No channels configured for angle {target_angle}°. Check [od_config.photodiode_channel]."
            )

    channel_summary = ", ".join(
        f"{channel}={angle}°"
        for channel, angle in sorted(channel_angle_map.items(), key=lambda item: int(item[0]))
    )
    return channel_angle_map, channel_summary


def _read_voltages_from_adc(
    channel_angle_map: dict[pt.PdChannel, pt.PdAngle],
) -> dict[pt.PdChannel, pt.Voltage]:
    signal_channels = sorted(channel_angle_map.keys(), key=int)

    with start_od_reading(
        config["od_config.photodiode_channel"],
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_testing_experiment_name(),
        calibration=False,
    ) as od_reader:

        for _ in range(3):
            od_reader.record_from_adc()

        od_readings1 = od_reader.record_from_adc()
        od_readings2 = od_reader.record_from_adc()
        od_readings3 = od_reader.record_from_adc()
        assert od_readings1 is not None
        assert od_readings2 is not None
        assert od_readings3 is not None
        averaged_readings = average_over_od_readings(od_readings1, od_readings2, od_readings3)
        return {channel: averaged_readings.ods[channel].od for channel in signal_channels}


def _measure_standard(
    od600_value: float,
    rpm: float,
    channel_angle_map: dict[pt.PdChannel, pt.PdAngle],
) -> dict[pt.PdChannel, pt.Voltage]:
    with stirring(
        target_rpm=rpm,
        unit=get_unit_name(),
        experiment=get_testing_experiment_name(),
    ) as st:
        st.block_until_rpm_is_close_to_target(abs_tolerance=120)
        sleep(1.0)
        return _read_voltages_from_adc(channel_angle_map)


def _measure_standard_for_session(
    ctx: SessionContext,
    od600_value: float,
    rpm: float,
    channel_angle_map: dict[pt.PdChannel, pt.PdAngle],
) -> dict[pt.PdChannel, pt.Voltage]:
    if ctx.executor and ctx.mode == "ui":
        payload = ctx.executor(
            "od_standards_measure",
            {
                "od600_value": od600_value,
                "rpm": rpm,
                "channel_angle_map": {str(k): str(v) for k, v in channel_angle_map.items()},
            },
        )
        raw = payload.get("voltages", {})
        return {cast(pt.PdChannel, channel): float(voltage) for channel, voltage in raw.items()}
    return _measure_standard(od600_value, rpm, channel_angle_map)


def _default_calibration_name() -> str:
    return f"od-cal-{current_utc_datestamp()}"


def _devices_for_angles(channel_angle_map: dict[pt.PdChannel, pt.PdAngle]) -> list[str]:
    return [f"od{angle}" for angle in sorted(channel_angle_map.values(), key=int)]


def _calculate_curve_data(
    od600_values: list[float],
    voltages: list[float],
) -> list[float]:
    degree = min(3, max(1, len(od600_values) - 1))
    weights = [1.0] * len(voltages)
    weights[0] = len(voltages) / 2
    return utils.calculate_poly_curve_of_best_fit(od600_values, voltages, degree, weights)


def _build_standards_chart_metadata(
    od600_values: list[float],
    voltages_by_channel: dict[pt.PdChannel, list[float]],
    channel_angle_map: dict[pt.PdChannel, pt.PdAngle],
) -> dict[str, object] | None:
    if not od600_values:
        return None

    series = []
    for channel, angle in sorted(channel_angle_map.items(), key=lambda item: int(item[0])):
        voltages = voltages_by_channel.get(channel, [])
        count = min(len(od600_values), len(voltages))
        if count <= 0:
            continue
        points = [{"x": float(od600_values[i]), "y": float(voltages[i])} for i in range(count)]
        curve = None
        if count > 1:
            curve = {"type": "poly", "coefficients": _calculate_curve_data(od600_values[:count], voltages[:count])}
        series.append(
            {
                "id": str(channel),
                "label": f"{channel} ({angle}°)",
                "points": points,
                "curve": curve,
            }
        )

    if not series:
        return None

    return {
        "title": "Calibration progress",
        "x_label": "OD600",
        "y_label": "Voltage",
        "series": series,
    }


def start_standards_session(target_device: pt.ODCalibrationDevices) -> CalibrationSession:
    if config.get("od_reading.config", "ir_led_intensity") == "auto":
        raise ValueError(
            "ir_led_intensity cannot be auto for OD calibrations. Set a numeric value in config.ini."
        )

    if any(is_pio_job_running(["stirring", "od_reading"])):
        raise ValueError("Both stirring and OD reading must be off before starting.")

    channel_angle_map, channel_summary = _channel_angle_map_from_config(target_device)
    devices_for_name_check = _devices_for_angles(channel_angle_map)

    session_id = str(uuid.uuid4())
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id=session_id,
        protocol_name=StandardsODProtocol.protocol_name,
        target_device=target_device,
        status="in_progress",
        step_id="intro",
        data={
            "channel_angle_map": to_builtins(channel_angle_map),
            "channel_summary": channel_summary,
            "devices_for_name_check": devices_for_name_check,
            "od600_values": [],
            "voltages_by_channel": {channel: [] for channel in channel_angle_map},
            "rpm": config.getfloat("stirring.config", "initial_target_rpm"),
        },
        created_at=now,
        updated_at=now,
    )


def od_standards_flow(ctx: SessionContext) -> CalibrationStep:
    if ctx.session.status != "in_progress":
        if ctx.session.result is not None:
            return steps.result(ctx.session.result)
        return steps.info("Calibration ended", "This calibration session has ended.")

    channel_angle_map = {
        cast(pt.PdChannel, channel): cast(pt.PdAngle, angle)
        for channel, angle in ctx.data.get("channel_angle_map", {}).items()
    }

    if ctx.step == "intro":
        if ctx.inputs.has_inputs:
            ctx.step = "name_input"
        return steps.info(
            "OD standards calibration",
            (
                "This routine calibrates the Pioreactor to OD600 readings using standards. "
                "You will need:\n"
                "1. A Pioreactor.\n"
                "2. A set of OD600 standards in Pioreactor vials (at least 10 mL each), with stir bars.\n"
                "3. One standard should be a blank (media only)."
            ),
        )

    if ctx.step == "name_input":
        default_name = ctx.data.setdefault("default_name", _default_calibration_name())
        if ctx.inputs.has_inputs:
            name = ctx.inputs.str("calibration_name", default=default_name)
            if name == "":
                raise ValueError("Calibration name cannot be empty.")
            devices_for_name_check = ctx.data.get("devices_for_name_check", [])
            existing = set()
            for device in devices_for_name_check:
                existing.update(list_of_calibrations_by_device(device))
            if name in existing:
                ctx.data["pending_name"] = name
                ctx.step = "name_overwrite_confirm"
            else:
                ctx.data["calibration_name"] = name
                ctx.step = "channel_confirm"
        return steps.form(
            "Name calibration",
            "Provide a name for this calibration.",
            [fields.str("calibration_name", label="Calibration name", default=default_name)],
        )

    if ctx.step == "name_overwrite_confirm":
        pending_name = ctx.data.get("pending_name", _default_calibration_name())
        if ctx.inputs.has_inputs:
            overwrite = ctx.inputs.choice("overwrite", ["yes", "no"], default="no")
            if overwrite == "yes":
                if not pending_name:
                    raise ValueError("Missing pending calibration name.")
                ctx.data["calibration_name"] = pending_name
                ctx.data.pop("pending_name", None)
                ctx.step = "channel_confirm"
            else:
                ctx.data.pop("pending_name", None)
                ctx.step = "name_input"
        return steps.form(
            "Name already exists",
            f"Calibration name '{pending_name}' already exists. Overwrite it?",
            [
                fields.choice(
                    "overwrite", ["yes", "no"], label="Overwrite existing calibration?", default="no"
                )
            ],
        )

    if ctx.step == "channel_confirm":
        if ctx.inputs.has_inputs:
            ctx.step = "rpm_input"
        channel_summary = ctx.data.get("channel_summary", "")
        return steps.info("Confirm channels", f"Using channels {channel_summary}.")

    if ctx.step == "rpm_input":
        default_rpm = ctx.data.get("rpm", config.getfloat("stirring.config", "initial_target_rpm"))
        if ctx.inputs.has_inputs:
            rpm = ctx.inputs.float("rpm", minimum=0, maximum=10000, default=default_rpm)
            ctx.data["rpm"] = rpm
            ctx.step = "place_standard"
        return steps.form(
            "Stirring setup",
            "Optional: set stirring RPM used during readings.",
            [fields.float("rpm", label="Stirring RPM", default=default_rpm, minimum=0, maximum=10000)],
        )

    if ctx.step == "place_standard":
        if ctx.inputs.has_inputs:
            ctx.step = "measure_standard"
        step = steps.info(
            "Place standard",
            "Place a non-blank standard vial with a stir bar into the Pioreactor.",
        )
        chart = _build_standards_chart_metadata(
            ctx.data.get("od600_values", []),
            ctx.data.get("voltages_by_channel", {}),
            channel_angle_map,
        )
        if chart:
            step.metadata = {"chart": chart}
        return step

    if ctx.step == "measure_standard":
        if ctx.inputs.has_inputs:
            od600_value = ctx.inputs.float("od600_value", minimum=0)
            voltages = _measure_standard_for_session(ctx, od600_value, ctx.data["rpm"], channel_angle_map)
            ctx.data["od600_values"].append(od600_value)
            for channel, voltage in voltages.items():
                ctx.data["voltages_by_channel"][channel].append(voltage)
            ctx.step = "another_standard"
        step = steps.form(
            "Record standard",
            "Enter the OD600 measurement for the current vial.",
            [fields.float("od600_value", label="OD600 value", minimum=0)],
        )
        chart = _build_standards_chart_metadata(
            ctx.data.get("od600_values", []),
            ctx.data.get("voltages_by_channel", {}),
            channel_angle_map,
        )
        if chart:
            step.metadata = {"chart": chart}
        return step

    if ctx.step == "another_standard":
        if ctx.inputs.has_inputs:
            action = None
            if ctx.inputs.raw is not None:
                action = ctx.inputs.raw.get("action")
            if action == "redo_last":
                if ctx.data.get("od600_values"):
                    ctx.data["od600_values"].pop()
                    for channel in ctx.data["voltages_by_channel"]:
                        if ctx.data["voltages_by_channel"][channel]:
                            ctx.data["voltages_by_channel"][channel].pop()
                ctx.step = "place_standard"
            else:
                next_action = ctx.inputs.choice(
                    "next_action",
                    ["record another standard", "continue to blank"],
                    default="record another standard",
                )
                if next_action == "record another standard":
                    ctx.step = "place_standard"
                else:
                    ctx.step = "place_blank"
        step = steps.form(
            "Next standard",
            "Record another standard or redo the last measurement?",
            [
                fields.choice(
                    "next_action",
                    ["record another standard", "continue to blank"],
                    label="Next action",
                    default="record another standard",
                )
            ],
        )
        step.metadata = {
            "actions": [
                {"label": "Redo last measurement", "inputs": {"action": "redo_last"}},
            ]
        }
        chart = _build_standards_chart_metadata(
            ctx.data.get("od600_values", []),
            ctx.data.get("voltages_by_channel", {}),
            channel_angle_map,
        )
        if chart:
            step.metadata = {**step.metadata, "chart": chart} if step.metadata else {"chart": chart}
        return step

    if ctx.step == "place_blank":
        if ctx.inputs.has_inputs:
            ctx.step = "measure_blank"
        step = steps.info(
            "Place blank",
            "Place the blank (media only) standard vial into the Pioreactor.",
        )
        chart = _build_standards_chart_metadata(
            ctx.data.get("od600_values", []),
            ctx.data.get("voltages_by_channel", {}),
            channel_angle_map,
        )
        if chart:
            step.metadata = {"chart": chart}
        return step

    if ctx.step == "measure_blank":
        if ctx.inputs.has_inputs:
            od600_blank = ctx.inputs.float("od600_blank", minimum=0)
            voltages = _measure_standard_for_session(ctx, od600_blank, ctx.data["rpm"], channel_angle_map)
            ctx.data["od600_values"].append(od600_blank)
            for channel, voltage in voltages.items():
                ctx.data["voltages_by_channel"][channel].append(voltage)

            calibration_links: list[dict[str, str | None]] = []
            for pd_channel, angle in sorted(channel_angle_map.items(), key=lambda item: int(item[0])):
                voltages_list = ctx.data["voltages_by_channel"][pd_channel]
                od600_values = ctx.data["od600_values"]
                curve_data_ = _calculate_curve_data(od600_values, voltages_list)
                cal = to_struct(
                    curve_data_,
                    "poly",
                    voltages_list,
                    od600_values,
                    angle,
                    ctx.data["calibration_name"],
                    pd_channel,
                    get_unit_name(),
                )
                device = f"od{angle}"
                calibration_links.append(ctx.store_calibration(cal, device))

            ctx.complete({"calibrations": calibration_links})
        step = steps.form(
            "Record blank",
            "Enter the OD600 measurement for the blank.",
            [fields.float("od600_blank", label="Blank OD600 value", minimum=0)],
        )
        chart = _build_standards_chart_metadata(
            ctx.data.get("od600_values", []),
            ctx.data.get("voltages_by_channel", {}),
            channel_angle_map,
        )
        if chart:
            step.metadata = {"chart": chart}
        return step

    return steps.info("Unknown step", "This step is not recognized.")


def advance_standards_session(
    session: CalibrationSession,
    inputs: dict[str, object],
    executor: SessionExecutor | None = None,
) -> CalibrationSession:
    engine = SessionEngine(flow=od_standards_flow, session=session, mode="ui", executor=executor)
    engine.advance(inputs)
    return engine.session


def get_standards_step(
    session: CalibrationSession, executor: SessionExecutor | None = None
) -> CalibrationStep | None:
    engine = SessionEngine(flow=od_standards_flow, session=session, mode="ui", executor=executor)
    return engine.get_step()


class StandardsODProtocol(CalibrationProtocol[pt.ODCalibrationDevices]):
    target_device = pt.OD_DEVICES
    protocol_name = "standards"
    description = "Calibrate OD using standards. Requires multiple vials"

    def run(  # type: ignore
        self, target_device: pt.ODCalibrationDevices, *args, **kwargs
    ) -> structs.OD600Calibration | list[structs.OD600Calibration]:
        session = start_standards_session(target_device)
        return run_session_in_cli(od_standards_flow, session)
