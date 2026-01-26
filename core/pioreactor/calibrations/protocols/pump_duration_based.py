# -*- coding: utf-8 -*-
import uuid
from configparser import NoOptionError
from typing import Callable
from typing import cast
from typing import ClassVar
from typing import Literal

from msgspec import to_builtins
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.calibrations import list_of_calibrations_by_device
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
        curve_data_=structs.PolyFitCoefficients(coefficients=[duration_, bias_]),
        hz=hz,
        dc=dc,
        voltage=voltage,
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
        curve_data_=structs.PolyFitCoefficients(coefficients=[1.0, 0.0]),
        hz=hz,
        dc=dc,
        voltage=voltage_in_aux(),
        calibrated_on_pioreactor_unit=unit,
        recorded_data={"x": [], "y": []},
    )


def _build_duration_chart_metadata(ctx: SessionContext) -> dict[str, object] | None:
    durations = ctx.data["durations_to_test"]
    results = ctx.data["results"]
    count = min(len(durations), len(results))
    points = [{"x": float(durations[i]), "y": float(results[i])} for i in range(count)]
    return {
        "title": "Calibration progress",
        "x_label": "Duration (s)",
        "y_label": "Volume (mL)",
        "series": [{"id": "measured", "label": "Measured", "points": points}],
    }


def _execute_pump_for_calibration(
    ctx: SessionContext,
    pump_device: PumpCalibrationDevices,
    duration_s: float,
) -> None:
    if ctx.executor and ctx.mode == "ui":
        ctx.executor(
            "pump",
            {
                "pump_device": pump_device,
                "duration_s": duration_s,
                "hz": float(ctx.data["hz"]),
                "dc": float(ctx.data["dc"]),
            },
        )
        return
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


def start_duration_based_session(pump_device: PumpCalibrationDevices) -> CalibrationSession:
    try:
        channel_pump_is_configured_for = config.get("PWM_reverse", pump_device.removesuffix("_pump"))
    except NoOptionError as exc:
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


def _get_pump_device(ctx: SessionContext) -> PumpCalibrationDevices:
    return cast(PumpCalibrationDevices, ctx.session.target_device)


def _get_default_calibration_name(ctx: SessionContext) -> str:
    pump_device = _get_pump_device(ctx)
    default_name = ctx.data.get("default_name")
    if default_name is None:
        default_name = f"{pump_device}-{current_utc_datestamp()}"
        ctx.data["default_name"] = default_name
    return default_name


class IntroConfirm1(SessionStep):
    step_id = "intro_confirm_1"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        pump_device = _get_pump_device(ctx)
        channel = ctx.data["channel_pump_is_configured_for"]
        return steps.info(
            "Pump calibration",
            (
                f"This routine calibrates the {pump_device} pump. You will need:\n"
                "1. Pioreactor hardware.\n"
                "2. A vial on a scale (0.1g resolution) or a graduated cylinder.\n"
                "3. A larger container filled with water.\n"
                f"4. {pump_device} connected to PWM channel {channel}.\n\n"
                "We will dose for set durations, you will measure the volume expelled, "
                "and record it to build a calibration curve."
            ),
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return IntroConfirm2()
        return None


class IntroConfirm2(SessionStep):
    step_id = "intro_confirm_2"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.info(
            "Keep hardware safe",
            "Keep liquids away from the Pioreactor hardware while running this calibration.",
        )
        step.metadata = {
            "image": {
                "src": "/static/svgs/no-no-vial.svg",
                "alt": "Keep liquids away from the Pioreactor hardware while running this calibration.",
                "caption": "Keep liquids away from the Pioreactor hardware.",
            }
        }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return IntroConfirm3()
        return None


class IntroConfirm3(SessionStep):
    step_id = "intro_confirm_3"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.info(
            "Keep hardware safe",
            "Make space between the vial and Pioreactor hardware",
        )
        step.metadata = {
            "image": {
                "src": "/static/svgs/keep-liquids-away.svg",
                "alt": "Move the vial and pump sink away from the hardware.",
                "caption": "Move the vial and tubing away from the hardware.",
            }
        }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return NameInput()
        return None


class NameInput(SessionStep):
    step_id = "name_input"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        default_name = _get_default_calibration_name(ctx)
        return steps.form(
            "Name calibration",
            "Provide a name for this calibration.",
            [fields.str("calibration_name", label="Calibration name", default=default_name)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        default_name = _get_default_calibration_name(ctx)
        name = ctx.inputs.str("calibration_name", default=default_name)
        existing_calibrations = list_of_calibrations_by_device(_get_pump_device(ctx))
        if name in existing_calibrations:
            ctx.data["pending_name"] = name
            return NameOverwriteConfirm()
        ctx.data["calibration_name"] = name
        return VolumeTargets()


class NameOverwriteConfirm(SessionStep):
    step_id = "name_overwrite_confirm"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        pending_name = ctx.data["pending_name"]
        return steps.form(
            "Name already exists",
            f"Calibration name '{pending_name}' already exists.",
            [fields.bool("overwrite", label="Overwrite existing calibration?", default=False)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        pending_name = ctx.data["pending_name"]
        overwrite = ctx.inputs.bool("overwrite", default=False)
        if overwrite:
            ctx.data["calibration_name"] = pending_name
            ctx.data.pop("pending_name", None)
            return VolumeTargets()
        ctx.data.pop("pending_name", None)
        return NameInput()


class VolumeTargets(SessionStep):
    step_id = "volume_targets"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Target volumes",
            "Enter the volumes you want to calibrate around (mL).",
            [fields.float_list("mls_to_calibrate_for", label="Target volumes (mL)", default=[1.0])],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        mls = ctx.inputs.float_list("mls_to_calibrate_for", default=[1.0])
        ctx.data["mls_to_calibrate_for"] = mls
        return PwmSettings()


class PwmSettings(SessionStep):
    step_id = "pwm_settings"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "PWM settings",
            "Optional: customize PWM settings for this calibration.",
            [
                fields.float("hz", label="PWM frequency (Hz)", default=250.0, minimum=0.1, maximum=10000),
                fields.float("dc", label="Duty cycle percent", default=100.0, minimum=0, maximum=100),
            ],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        hz = ctx.inputs.float("hz", minimum=0.1, maximum=10000, default=250.0)
        dc = ctx.inputs.float("dc", minimum=0, maximum=100, default=100.0)
        ctx.data["hz"] = hz
        ctx.data["dc"] = dc
        return TubingIntoWater()


class TubingIntoWater(SessionStep):
    step_id = "tubing_into_water"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        pump_device = _get_pump_device(ctx)
        step = steps.info(
            f"Place tubing ends of {pump_device} in water",
            f"Place both ends of the {pump_device} tubing into the larger container of water to prime.",
        )
        step.metadata = {
            "image": {
                "src": "/static/svgs/tubing-ends-in-water.svg",
                "alt": "Place both ends of the tubing into the larger water container.",
                "caption": "Both tubing ends should sit below the water line.",
            }
        }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return PrimePumpDuration()
        return None


class PrimePumpDuration(SessionStep):
    step_id = "prime_pump_duration"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Prime pump",
            "Prime the pump by filling the tubes completely with water. There should be no air pockets by the end.",
            [fields.float("prime_duration_s", label="Prime duration (seconds)", default=15.0, minimum=5)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        duration_s = ctx.inputs.float("prime_duration_s", minimum=0.1, default=20.0)
        _execute_pump_for_calibration(ctx, _get_pump_device(ctx), duration_s)
        ctx.data["prime_duration_s"] = duration_s
        ctx.data["tracer_duration_s"] = ctx.data.get("tracer_duration_s", 1.0)
        return TracerRun()


class TracerRun(SessionStep):
    step_id = "tracer_run"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        tracer_duration = float(ctx.data["tracer_duration_s"])
        step = steps.action(
            "Tracer run",
            (
                f"Running the pump for {tracer_duration:.2f} seconds.\n\n"
                "While running, hold the tube above the vial. Please measure the volume expelled.\n\n"
                "Ready?"
            ),
        )
        step.metadata = {
            "image": {
                "src": "/static/svgs/pump-measure-volume.svg",
                "alt": "Run the pump briefly and measure the volume expelled using a scale.",
                "caption": "Measure the volume expelled on a scale or graduated cylinder.",
            }
        }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        tracer_duration = float(ctx.data["tracer_duration_s"])
        _execute_pump_for_calibration(ctx, _get_pump_device(ctx), tracer_duration)
        return TracerVolume()


class TracerVolume(SessionStep):
    step_id = "tracer_volume"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Tracer volume",
            "Enter the amount of water expelled (mL or g).",
            [fields.float("volume_ml", label="Volume expelled", minimum=0.0001)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        tracer_ml = ctx.inputs.float("volume_ml", minimum=0.0001)
        mls_to_calibrate_for = ctx.data["mls_to_calibrate_for"]
        tracer_duration = float(ctx.data.get("tracer_duration_s", 1.0))
        min_duration = min(mls_to_calibrate_for) * 0.8 / tracer_ml * tracer_duration
        max_duration = max(mls_to_calibrate_for) * 1.1 / tracer_ml * tracer_duration
        durations_to_test = [min_duration] * 4 + [(min_duration + max_duration) / 2] * 2 + [max_duration] * 4
        ctx.data["tracer_ml"] = tracer_ml
        ctx.data["min_duration"] = min_duration
        ctx.data["max_duration"] = max_duration
        ctx.data["durations_to_test"] = durations_to_test
        ctx.data["results"] = []
        ctx.data["test_index"] = 0
        return TestRun()


class TestRun(SessionStep):
    step_id = "test_run"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        durations = ctx.data["durations_to_test"]
        test_index = int(ctx.data["test_index"])
        results = ctx.data["results"]
        duration = float(durations[test_index])
        step = steps.action(
            "Dispense",
            f"Next: running the pump for {duration:.2f} seconds. Please measure the volume expelled. \n\nReady?",
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
        else:
            step.metadata = {
                "image": {
                    "src": "/static/svgs/pump-measure-volume.svg",
                    "alt": "Run the pump briefly and measure the volume expelled using a scale.",
                    "caption": "Measure the volume expelled on a scale or graduated cylinder.",
                }
            }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        durations = ctx.data["durations_to_test"]
        test_index = int(ctx.data["test_index"])
        results = ctx.data["results"]
        action = ctx.inputs.raw.get("action")  # type: ignore
        if action == "redo_last":
            results.pop()
            test_index = max(test_index - 1, 0)
            ctx.data["test_index"] = test_index
        duration = float(durations[test_index])
        _execute_pump_for_calibration(ctx, _get_pump_device(ctx), duration)
        return TestVolume()


class TestVolume(SessionStep):
    step_id = "test_volume"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.form(
            "Record dispensed volume",
            "Enter the amount of water expelled (mL or g).",
            [fields.float("volume_ml", label="Volume expelled", minimum=0.0001)],
        )
        chart = _build_duration_chart_metadata(ctx)
        if chart:
            step.metadata = {"chart": chart}
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        volume_ml = ctx.inputs.float("volume_ml", minimum=0.0001)
        results = ctx.data["results"]
        results.append(volume_ml)
        ctx.data["results"] = results
        ctx.data["test_index"] = int(ctx.data["test_index"]) + 1
        if ctx.data["test_index"] < len(ctx.data["durations_to_test"]):
            return TestRun()
        durations = ctx.data["durations_to_test"]
        (slope, std_slope), (bias, std_bias) = simple_linear_regression_with_forced_nil_intercept(
            durations, results
        )
        pump_device = _get_pump_device(ctx)
        calibration_struct = save_results(
            name=ctx.data["calibration_name"],
            pump_device=pump_device,
            duration_=slope,
            bias_=bias,
            hz=float(ctx.data["hz"]),
            dc=float(ctx.data["dc"]),
            voltage=ctx.read_voltage() if ctx.mode == "ui" else voltage_in_aux(),
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
        return CalibrationComplete()


_PUMP_DURATION_STEPS: StepRegistry = {
    IntroConfirm1.step_id: IntroConfirm1,
    IntroConfirm2.step_id: IntroConfirm2,
    IntroConfirm3.step_id: IntroConfirm3,
    TubingIntoWater.step_id: TubingIntoWater,
    NameInput.step_id: NameInput,
    NameOverwriteConfirm.step_id: NameOverwriteConfirm,
    VolumeTargets.step_id: VolumeTargets,
    PwmSettings.step_id: PwmSettings,
    PrimePumpDuration.step_id: PrimePumpDuration,
    TracerRun.step_id: TracerRun,
    TracerVolume.step_id: TracerVolume,
    TestRun.step_id: TestRun,
    TestVolume.step_id: TestVolume,
}


def run_pump_calibration(
    pump_device: PumpCalibrationDevices,
) -> structs.SimplePeristalticPumpCalibration:
    session = start_duration_based_session(pump_device)
    calibrations = run_session_in_cli(_PUMP_DURATION_STEPS, session)
    return calibrations[0]


class DurationBasedPumpProtocol(CalibrationProtocol):
    target_device = cast(list[pt.PumpCalibrationDevices], pt.PUMP_DEVICES)
    protocol_name = "duration_based"
    title = "Duration-based pump calibration"
    description = "Build a duration-to-volume curve for the {device} using a simple multi-step flow."
    requirements = (
        "DC Peristaltic pump assigned to {device}",
        "Pioreactor vial",
        "Container of clean water",
        "Measuring container or scale",
    )
    step_registry: ClassVar[StepRegistry] = _PUMP_DURATION_STEPS

    @classmethod
    def start_session(cls, target_device: pt.PumpCalibrationDevices) -> CalibrationSession:
        return start_duration_based_session(target_device)

    def run(
        self, target_device: pt.PumpCalibrationDevices, **kwargs
    ) -> structs.SimplePeristalticPumpCalibration:
        return run_pump_calibration(target_device)
