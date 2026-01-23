# -*- coding: utf-8 -*-
"""
Copyright 2023 Chris Macdonald, Pioreactor

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
import uuid
from time import sleep
from typing import cast
from typing import ClassVar

from msgspec import to_builtins
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import average_over_od_readings
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations import utils
from pioreactor.calibrations.registry import CalibrationProtocol
from pioreactor.calibrations.session_flow import CalibrationComplete
from pioreactor.calibrations.session_flow import fields
from pioreactor.calibrations.session_flow import run_session_in_cli
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionStep
from pioreactor.calibrations.session_flow import StepRegistry
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.config import config
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


def to_struct(
    curve_data_: structs.CalibrationCurveData,
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
        recorded_data={"x": od600s, "y": voltages},
        ir_led_intensity=float(config["od_reading.config"]["ir_led_intensity"]),
        pd_channel=pd_channel,
    )

    return data_blob


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
    from pioreactor.background_jobs.stirring import start_stirring as stirring

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
        if not isinstance(raw, dict):
            raise ValueError("Invalid voltage payload.")
        return {cast(pt.PdChannel, channel): float(voltage) for channel, voltage in raw.items()}
    return _measure_standard(od600_value, rpm, channel_angle_map)


def _default_calibration_name() -> str:
    return f"od-cal-{current_utc_datestamp()}"


def _devices_for_angles(channel_angle_map: dict[pt.PdChannel, pt.PdAngle]) -> list[str]:
    return [f"od{angle}" for angle in sorted(channel_angle_map.values(), key=int)]


def _calculate_curve_data(
    od600_values: list[float],
    voltages: list[float],
) -> structs.CalibrationCurveData:
    weights = [1.0] * len(voltages)
    weights[0] = len(voltages) / 2
    if len(od600_values) >= 3:
        from pioreactor.utils.splines import spline_fit

        return spline_fit(od600_values, voltages, knots="auto", weights=weights)

    degree = min(3, max(1, len(od600_values) - 1))
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
            curve_data = _calculate_curve_data(od600_values[:count], voltages[:count])
            curve = to_builtins(curve_data)
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


def _get_channel_angle_map(ctx: SessionContext) -> dict[pt.PdChannel, pt.PdAngle]:
    return {
        cast(pt.PdChannel, channel): cast(pt.PdAngle, angle)
        for channel, angle in ctx.data.get("channel_angle_map", {}).items()
    }


class Intro(SessionStep):
    step_id = "intro"

    def render(self, ctx: SessionContext) -> CalibrationStep:
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

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return NameInput()
        return None


class NameInput(SessionStep):
    step_id = "name_input"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        default_name = ctx.data.setdefault("default_name", _default_calibration_name())
        return steps.form(
            "Name calibration",
            "Provide a name for this calibration.",
            [fields.str("calibration_name", label="Calibration name", default=default_name)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        default_name = ctx.data.setdefault("default_name", _default_calibration_name())
        name = ctx.inputs.str("calibration_name", default=default_name)
        if name == "":
            raise ValueError("Calibration name cannot be empty.")
        devices_for_name_check = ctx.data.get("devices_for_name_check", [])
        existing = set()
        for device in devices_for_name_check:
            existing.update(list_of_calibrations_by_device(device))
        if name in existing:
            ctx.data["pending_name"] = name
            return NameOverwriteConfirm()
        ctx.data["calibration_name"] = name
        return ChannelConfirm()


class NameOverwriteConfirm(SessionStep):
    step_id = "name_overwrite_confirm"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        pending_name = ctx.data.get("pending_name", _default_calibration_name())
        return steps.form(
            "Name already exists",
            f"Calibration name '{pending_name}' already exists. Overwrite it?",
            [fields.bool("overwrite", label="Overwrite existing calibration?", default=False)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        pending_name = ctx.data.get("pending_name", _default_calibration_name())
        overwrite = ctx.inputs.bool("overwrite", default=False)
        if overwrite:
            if not pending_name:
                raise ValueError("Missing pending calibration name.")
            ctx.data["calibration_name"] = pending_name
            ctx.data.pop("pending_name", None)
            return ChannelConfirm()
        ctx.data.pop("pending_name", None)
        return NameInput()


class ChannelConfirm(SessionStep):
    step_id = "channel_confirm"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        channel_summary = ctx.data.get("channel_summary", "")
        channel_lines = channel_summary.split(", ") if channel_summary else []
        if channel_lines:
            message = "Using channels:\n" + "\n".join(channel_lines)
        else:
            message = "Using channels."
        return steps.info("Confirm channels", message)

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return RpmInput()
        return None


class RpmInput(SessionStep):
    step_id = "rpm_input"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        default_rpm = ctx.data.get("rpm", config.getfloat("stirring.config", "initial_target_rpm"))
        return steps.form(
            "Stirring setup",
            "Optional: set stirring RPM used during readings.",
            [fields.float("rpm", label="Stirring RPM", default=default_rpm, minimum=0, maximum=10000)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        default_rpm = ctx.data.get("rpm", config.getfloat("stirring.config", "initial_target_rpm"))
        rpm = ctx.inputs.float("rpm", minimum=0, maximum=10000, default=default_rpm)
        ctx.data["rpm"] = rpm
        return PlaceStandard()


class PlaceStandard(SessionStep):
    step_id = "place_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.info(
            "Place standard",
            "Place a non-blank standard vial with a stir bar into the Pioreactor.",
        )
        chart = _build_standards_chart_metadata(
            ctx.data.get("od600_values", []),
            ctx.data.get("voltages_by_channel", {}),
            _get_channel_angle_map(ctx),
        )
        if chart:
            step.metadata["chart"] = chart
        else:
            step.metadata = {
                "image": {
                    "src": "/static/svgs/place-standard-arrow-pioreactor.svg",
                    "alt": "Place a non-blank standard vial with a stir bar into the Pioreactor.",
                    "caption": "Place a non-blank standard vial with a stir bar into the Pioreactor.",
                }
            }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return MeasureStandard()
        return None


class MeasureStandard(SessionStep):
    step_id = "measure_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.form(
            "Record standard",
            "Enter the OD600 measurement for the current vial.",
            [fields.float("od600_value", label="OD600 value", minimum=0)],
        )
        chart = _build_standards_chart_metadata(
            ctx.data.get("od600_values", []),
            ctx.data.get("voltages_by_channel", {}),
            _get_channel_angle_map(ctx),
        )
        if chart:
            step.metadata = {"chart": chart}
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        channel_angle_map = _get_channel_angle_map(ctx)
        od600_value = ctx.inputs.float("od600_value", minimum=0)
        voltages = _measure_standard_for_session(ctx, od600_value, ctx.data["rpm"], channel_angle_map)
        ctx.data["od600_values"].append(od600_value)
        for channel, voltage in voltages.items():
            ctx.data["voltages_by_channel"][channel].append(voltage)
        return AnotherStandard()


class AnotherStandard(SessionStep):
    step_id = "another_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.form(
            "Next standard",
            "Record another standard, move on to the blank, or redo the last measurement?",
            [
                fields.choice(
                    "next_action",
                    ["record another standard", "finish, and continue to blank"],
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
            _get_channel_angle_map(ctx),
        )
        if chart:
            step.metadata = {**step.metadata, "chart": chart} if step.metadata else {"chart": chart}
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        action = None
        if ctx.inputs.raw is not None:
            action = ctx.inputs.raw.get("action")
        if action == "redo_last":
            if ctx.data.get("od600_values"):
                ctx.data["od600_values"].pop()
                for channel in ctx.data["voltages_by_channel"]:
                    if ctx.data["voltages_by_channel"][channel]:
                        ctx.data["voltages_by_channel"][channel].pop()
            return PlaceStandard()
        next_action = ctx.inputs.choice(
            "next_action",
            ["record another standard", "finish, and continue to blank"],
            default="record another standard",
        )
        if next_action == "record another standard":
            return PlaceStandard()
        return PlaceBlank()


class PlaceBlank(SessionStep):
    step_id = "place_blank"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.info(
            "Place blank",
            "Place the blank (media only) standard vial into the Pioreactor.",
        )
        step.metadata = {
            "image": {
                "src": "/static/svgs/place-blank-arrow-pioreactor.svg",
                "alt": "Place the blank (media only) standard vial into the Pioreactor.",
                "caption": "Place the blank (media only) standard vial into the Pioreactor.",
            }
        }

        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return MeasureBlank()
        return None


class MeasureBlank(SessionStep):
    step_id = "measure_blank"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.form(
            "Record blank",
            "Enter the OD600 measurement for the blank.",
            [fields.float("od600_blank", label="Blank OD600 value", minimum=0)],
        )
        chart = _build_standards_chart_metadata(
            ctx.data.get("od600_values", []),
            ctx.data.get("voltages_by_channel", {}),
            _get_channel_angle_map(ctx),
        )
        if chart:
            step.metadata = {"chart": chart}
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        channel_angle_map = _get_channel_angle_map(ctx)
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
        return CalibrationComplete()


_OD_STANDARDS_STEPS: StepRegistry = {
    Intro.step_id: Intro,
    NameInput.step_id: NameInput,
    NameOverwriteConfirm.step_id: NameOverwriteConfirm,
    ChannelConfirm.step_id: ChannelConfirm,
    RpmInput.step_id: RpmInput,
    PlaceStandard.step_id: PlaceStandard,
    MeasureStandard.step_id: MeasureStandard,
    AnotherStandard.step_id: AnotherStandard,
    PlaceBlank.step_id: PlaceBlank,
    MeasureBlank.step_id: MeasureBlank,
}


def get_valid_od_devices_for_this_unit() -> list[pt.ODCalibrationDevices]:
    if is_testing_env():
        return [cast(pt.ODCalibrationDevices, device) for device in pt.OD_DEVICES]

    pd_channels = config["od_config.photodiode_channel"]
    valid_devices: list[pt.ODCalibrationDevices] = []

    for _, angle in pd_channels.items():
        if angle in (None, "", REF_keyword):
            continue
        device = f"od{angle}"
        if device in pt.OD_DEVICES and device not in valid_devices:
            valid_devices.append(cast(pt.ODCalibrationDevices, device))

    return valid_devices


class StandardsODProtocol(CalibrationProtocol[pt.ODCalibrationDevices]):
    target_device = get_valid_od_devices_for_this_unit()
    protocol_name = "standards"
    title = "OD standards calibration"
    description = "Calibrate OD channels using a series of OD600 standards and a blank."
    requirements = (
        "OD600 standards (including a blank)",
        "Vials",
        "Stir bars",
    )
    step_registry: ClassVar[StepRegistry] = _OD_STANDARDS_STEPS

    @classmethod
    def start_session(cls, target_device: pt.ODCalibrationDevices) -> CalibrationSession:
        return start_standards_session(target_device)

    def run(  # type: ignore
        self, target_device: pt.ODCalibrationDevices, *args, **kwargs
    ) -> structs.OD600Calibration | list[structs.OD600Calibration]:
        session = start_standards_session(target_device)
        return run_session_in_cli(_OD_STANDARDS_STEPS, session)
