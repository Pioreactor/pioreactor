# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from typing import Callable
from typing import Literal

from msgspec import to_builtins
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations.registry import CalibrationProtocol
from pioreactor.calibrations.session_flow import fields
from pioreactor.calibrations.session_flow import run_session_in_cli
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionEngine
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.config import config
from pioreactor.hardware import voltage_in_aux
from pioreactor.logging import create_logger
from pioreactor.types import PumpCalibrationDevices
from pioreactor.utils.math_helpers import correlation
from pioreactor.utils.math_helpers import simple_linear_regression_with_forced_nil_intercept
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name


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


def _get_execute_pump_for_device(pump_device: PumpCalibrationDevices) -> Callable:
    from pioreactor.actions.pump import add_alt_media
    from pioreactor.actions.pump import add_media
    from pioreactor.actions.pump import remove_waste

    if pump_device == "media_pump":
        return add_media
    if pump_device == "alt_media_pump":
        return add_alt_media
    if pump_device == "waste_pump":
        return remove_waste
    raise ValueError(f"Unknown pump device: {pump_device}")


def _build_transient_calibration(hz: float, dc: float, unit: str) -> structs.SimplePeristalticPumpCalibration:
    return structs.SimplePeristalticPumpCalibration(
        calibration_name="calibration",
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=[1, 0],
        hz=hz,
        dc=dc,
        voltage=voltage_in_aux(),
        calibrated_on_pioreactor_unit=unit,
        recorded_data={"x": [], "y": []},
    )


def _build_duration_chart_metadata(ctx: SessionContext) -> dict[str, object] | None:
    durations = ctx.data.get("durations_to_test", [])
    results = ctx.data.get("results", [])
    if not isinstance(durations, list) or not isinstance(results, list):
        return None
    count = min(len(durations), len(results))
    if count <= 0:
        return None
    points = [{"x": float(durations[i]), "y": float(results[i])} for i in range(count)]
    return {
        "title": "Calibration progress",
        "x_label": "Duration (s)",
        "y_label": "Volume (mL)",
        "series": [{"id": "measured", "label": "Measured", "points": points}],
    }


def start_duration_based_session(pump_device: PumpCalibrationDevices) -> CalibrationSession:
    try:
        channel_pump_is_configured_for = config.get("PWM_reverse", pump_device.removesuffix("_pump"))
    except KeyError as exc:
        raise ValueError(f"{pump_device} is not present in config.ini. Add it to the [PWM] section.") from exc

    session_id = str(uuid.uuid4())
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id=session_id,
        protocol_name=DurationBasedPumpProtocol.protocol_name,
        target_device=pump_device,
        status="in_progress",
        step_id="intro_confirm_1",
        data={"channel_pump_is_configured_for": channel_pump_is_configured_for},
        created_at=now,
        updated_at=now,
    )


def pump_duration_flow(ctx: SessionContext) -> CalibrationStep:
    if ctx.session.status != "in_progress":
        if ctx.session.result is not None:
            return steps.result(ctx.session.result)
        return steps.info("Calibration ended", "This calibration session has ended.")

    pump_device = ctx.session.target_device
    channel = ctx.data.get("channel_pump_is_configured_for")
    default_name = ctx.data.setdefault("default_name", f"{pump_device}-{current_utc_datestamp()}")

    if ctx.step == "intro_confirm_1":
        if ctx.inputs.has_inputs:
            ctx.step = "intro_confirm_2"
        return steps.info(
            "Pump calibration",
            (
                "This routine calibrates the pump on this Pioreactor. You will need:\n"
                "1. This Pioreactor.\n"
                "2. A vial on a scale (0.1g resolution) or a graduated cylinder.\n"
                "3. A larger container filled with water.\n"
                f"4. {pump_device} connected to PWM channel {channel}.\n\n"
                "We will dose for set durations, you will measure the volume expelled, "
                "and record it to build a calibration curve."
            ),
        )

    if ctx.step == "intro_confirm_2":
        if ctx.inputs.has_inputs:
            ctx.step = "name_input"
        step = steps.info(
            "Keep hardware safe",
            "Keep liquids away from the Pioreactor while running this calibration.",
        )
        step.metadata = {
            "image": {
                "src": "/static/images/calibration-placeholder.png",
                "alt": "Keep liquids away from the Pioreactor while running this calibration.",
                "caption": "Keep liquids away from the Pioreactor.",
            }
        }
        return step

    if ctx.step == "name_input":
        if ctx.inputs.has_inputs:
            name = ctx.inputs.str("calibration_name", default=default_name)
            if name == "":
                raise ValueError("Calibration name cannot be empty.")
            existing_calibrations = list_of_calibrations_by_device(pump_device)
            if name in existing_calibrations:
                ctx.data["pending_name"] = name
                ctx.step = "name_overwrite_confirm"
            else:
                ctx.data["calibration_name"] = name
                ctx.step = "volume_targets"
        return steps.form(
            "Name calibration",
            "Provide a name for this calibration.",
            [fields.str("calibration_name", label="Calibration name", default=default_name)],
        )

    if ctx.step == "name_overwrite_confirm":
        pending_name = ctx.data.get("pending_name", default_name)
        if ctx.inputs.has_inputs:
            overwrite = ctx.inputs.choice("overwrite", ["yes", "no"], default="no")
            if overwrite == "yes":
                ctx.data["calibration_name"] = pending_name
                ctx.data.pop("pending_name", None)
                ctx.step = "volume_targets"
            else:
                ctx.data.pop("pending_name", None)
                ctx.step = "name_input"
        return steps.form(
            "Name already exists",
            f"Calibration name '{pending_name}' already exists.",
            [
                fields.choice(
                    "overwrite", ["yes", "no"], label="Overwrite existing calibration?", default="no"
                )
            ],
        )

    if ctx.step == "volume_targets":
        if ctx.inputs.has_inputs:
            mls = ctx.inputs.float_list("mls_to_calibrate_for", default=[1.0])
            if any(ml <= 0 for ml in mls):
                raise ValueError("All target volumes must be > 0.")
            ctx.data["mls_to_calibrate_for"] = mls
            ctx.step = "pwm_settings"
        return steps.form(
            "Target volumes",
            "Enter the volumes you want to calibrate around (mL).",
            [fields.float_list("mls_to_calibrate_for", label="Target volumes (mL)", default=[1.0])],
        )

    if ctx.step == "pwm_settings":
        if ctx.inputs.has_inputs:
            hz = ctx.inputs.float("hz", minimum=0.1, maximum=10000, default=250.0)
            dc = ctx.inputs.float("dc", minimum=0, maximum=100, default=100.0)
            ctx.data["hz"] = hz
            ctx.data["dc"] = dc
            ctx.step = "prime_pump_duration"
        return steps.form(
            "PWM settings",
            "Optional: customize PWM settings for this calibration.",
            [
                fields.float("hz", label="PWM frequency (Hz)", default=250.0, minimum=0.1, maximum=10000),
                fields.float("dc", label="Duty cycle percent", default=100.0, minimum=0, maximum=100),
            ],
        )

    if ctx.step == "prime_pump_duration":
        if ctx.inputs.has_inputs:
            duration_s = ctx.inputs.float("prime_duration_s", minimum=0.1, default=20.0)
            execute_pump = _get_execute_pump_for_device(pump_device)
            calibration = _build_transient_calibration(
                hz=float(ctx.data["hz"]), dc=float(ctx.data["dc"]), unit=get_unit_name()
            )
            execute_pump(
                duration=duration_s,
                source_of_event="pump_calibration",
                unit=get_unit_name(),
                experiment=get_testing_experiment_name(),
                calibration=calibration,
            )
            ctx.data["prime_duration_s"] = duration_s
            ctx.data.setdefault("tracer_duration_s", 1.0)
            ctx.step = "tracer_run"
        return steps.form(
            "Prime pump",
            "Prime the pump by filling the tubes completely with water.",
            [fields.float("prime_duration_s", label="Prime duration (seconds)", default=10.0, minimum=0.1)],
        )

    if ctx.step == "tracer_run":
        tracer_duration = float(ctx.data.get("tracer_duration_s", 1.0))
        if ctx.inputs.has_inputs:
            execute_pump = _get_execute_pump_for_device(pump_device)
            calibration = _build_transient_calibration(
                hz=float(ctx.data["hz"]), dc=float(ctx.data["dc"]), unit=get_unit_name()
            )
            execute_pump(
                duration=tracer_duration,
                source_of_event="pump_calibration",
                unit=get_unit_name(),
                experiment=get_testing_experiment_name(),
                calibration=calibration,
            )
            ctx.step = "tracer_volume"
        return steps.action(
            "Tracer run",
            f"Running the pump for {tracer_duration:.2f} seconds, then measure the volume expelled.",
        )

    if ctx.step == "tracer_volume":
        if ctx.inputs.has_inputs:
            tracer_ml = ctx.inputs.float("volume_ml", minimum=0.0001)
            mls_to_calibrate_for = ctx.data["mls_to_calibrate_for"]
            tracer_duration = float(ctx.data.get("tracer_duration_s", 1.0))
            min_duration = min(mls_to_calibrate_for) * 0.8 / tracer_ml * tracer_duration
            max_duration = max(mls_to_calibrate_for) * 1.1 / tracer_ml * tracer_duration
            durations_to_test = (
                [min_duration] * 4 + [(min_duration + max_duration) / 2] * 2 + [max_duration] * 4
            )
            ctx.data["tracer_ml"] = tracer_ml
            ctx.data["min_duration"] = min_duration
            ctx.data["max_duration"] = max_duration
            ctx.data["durations_to_test"] = durations_to_test
            ctx.data["results"] = []
            ctx.data["test_index"] = 0
            ctx.step = "test_run"
        return steps.form(
            "Tracer volume",
            "Enter the amount of water expelled (mL or g).",
            [fields.float("volume_ml", label="Volume expelled", minimum=0.0001)],
        )

    if ctx.step == "test_run":
        durations = ctx.data["durations_to_test"]
        test_index = int(ctx.data["test_index"])
        results = ctx.data.get("results", [])
        if ctx.inputs.has_inputs:
            action = None
            if ctx.inputs.raw is not None:
                action = ctx.inputs.raw.get("action")
            if action == "redo_last" and results:
                results.pop()
                ctx.data["results"] = results
                test_index = max(test_index - 1, 0)
                ctx.data["test_index"] = test_index
            duration = float(durations[test_index])
            execute_pump = _get_execute_pump_for_device(pump_device)
            calibration = _build_transient_calibration(
                hz=float(ctx.data["hz"]), dc=float(ctx.data["dc"]), unit=get_unit_name()
            )
            execute_pump(
                duration=duration,
                source_of_event="pump_calibration",
                unit=get_unit_name(),
                experiment=get_testing_experiment_name(),
                calibration=calibration,
            )
            ctx.step = "test_volume"
        duration = float(durations[test_index])
        step = steps.action(
            "Test run",
            f"Running the pump for {duration:.2f} seconds, then measure the volume expelled.",
        )
        if results:
            step.metadata = {
                "actions": [
                    {"label": "Redo last measurement", "inputs": {"action": "redo_last"}},
                ]
            }
        chart = _build_duration_chart_metadata(ctx)
        if chart:
            step.metadata = {**step.metadata, "chart": chart} if step.metadata else {"chart": chart}
        return step

    if ctx.step == "test_volume":
        if ctx.inputs.has_inputs:
            volume_ml = ctx.inputs.float("volume_ml", minimum=0.0001)
            results = ctx.data["results"]
            results.append(volume_ml)
            ctx.data["results"] = results
            ctx.data["test_index"] = int(ctx.data["test_index"]) + 1
            if ctx.data["test_index"] < len(ctx.data["durations_to_test"]):
                ctx.step = "test_run"
            else:
                durations = ctx.data["durations_to_test"]
                (slope, std_slope), (bias, std_bias) = simple_linear_regression_with_forced_nil_intercept(
                    durations, results
                )
                calibration_struct = save_results(
                    name=ctx.data["calibration_name"],
                    pump_device=pump_device,
                    duration_=slope,
                    bias_=bias,
                    hz=float(ctx.data["hz"]),
                    dc=float(ctx.data["dc"]),
                    voltage=voltage_in_aux(),
                    durations=durations,
                    volumes=results,
                    unit=get_unit_name(),
                )
                link = ctx.store_calibration(calibration_struct, pump_device)
                min_duration = float(ctx.data["min_duration"])
                max_duration = float(ctx.data["max_duration"])
                ctx.complete(
                    {
                        "calibration": to_builtins(calibration_struct),
                        "calibration_link": link,
                        "stats": {
                            "slope": slope,
                            "bias": bias,
                            "std_slope": std_slope,
                            "std_bias": std_bias,
                        },
                        "recommended_volume_range_ml": [
                            slope * min_duration + bias,
                            slope * max_duration + bias,
                        ],
                    }
                )
                logger = create_logger("pump_calibration", unit=get_unit_name(), experiment="$experiment")
                if correlation(durations, results) < 0:
                    logger.warning("Correlation is negative - you probably want to rerun this calibration...")
                if std_slope > 0.04:
                    logger.warning(
                        "Too much uncertainty in slope - you probably want to rerun this calibration..."
                    )
        step = steps.form(
            "Record test volume",
            "Enter the amount of water expelled (mL or g).",
            [fields.float("volume_ml", label="Volume expelled", minimum=0.0001)],
        )
        chart = _build_duration_chart_metadata(ctx)
        if chart:
            step.metadata = {"chart": chart}
        return step

    return steps.info("Unknown step", "This step is not recognized.")


def get_duration_based_step(session: CalibrationSession) -> CalibrationStep | None:
    engine = SessionEngine(flow=pump_duration_flow, session=session, mode="ui")
    return engine.get_step()


def advance_duration_based_session(
    session: CalibrationSession, inputs: dict[str, object]
) -> CalibrationSession:
    engine = SessionEngine(flow=pump_duration_flow, session=session, mode="ui")
    engine.advance(inputs)
    return engine.session


def run_pump_calibration(
    pump_device: PumpCalibrationDevices,
) -> structs.SimplePeristalticPumpCalibration:
    session = start_duration_based_session(pump_device)
    calibrations = run_session_in_cli(pump_duration_flow, session)
    if not calibrations:
        raise ValueError("Calibration finished without producing a result.")
    return calibrations[0]


class DurationBasedPumpProtocol(CalibrationProtocol[pt.PumpCalibrationDevices]):
    target_device = pt.PUMP_DEVICES
    protocol_name = "duration_based"

    def run(
        self, target_device: pt.PumpCalibrationDevices, **kwargs
    ) -> structs.SimplePeristalticPumpCalibration:
        return run_pump_calibration(target_device)
