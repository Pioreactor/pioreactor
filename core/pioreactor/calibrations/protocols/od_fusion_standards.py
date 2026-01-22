# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from math import exp
from math import log
from math import log10
from statistics import fmean
from typing import ClassVar
from typing import cast

from msgspec import to_builtins
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations.registry import CalibrationProtocol
from pioreactor.calibrations.session_flow import CalibrationComplete
from pioreactor.calibrations.session_flow import CalibrationStep
from pioreactor.calibrations.session_flow import fields
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionStep
from pioreactor.calibrations.session_flow import StepRegistry
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.config import config
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.od_fusion import FUSION_ANGLES
from pioreactor.utils.od_fusion import fit_fusion_model
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_pioreactor_model
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


MIN_SAMPLES_PER_STANDARD = 3


def _ensure_xr_model() -> None:
    model = get_pioreactor_model()
    if not model.model_name.endswith("_XR"):
        raise ValueError("Fusion calibration is only available on XR models.")


def _channel_angle_map_from_config() -> dict[pt.PdChannel, pt.PdAngle]:
    pd_channels = config["od_config.photodiode_channel"]
    channel_angle_map: dict[pt.PdChannel, pt.PdAngle] = {}
    for channel, angle in pd_channels.items():
        if angle in FUSION_ANGLES:
            channel_angle_map[cast(pt.PdChannel, channel)] = cast(pt.PdAngle, angle)

    configured_angles = {angle for angle in channel_angle_map.values()}
    missing = [angle for angle in FUSION_ANGLES if angle not in configured_angles]
    if missing:
        raise ValueError(
            "Fusion calibration requires PD channels configured for angles "
            f"{', '.join(missing)}. Check [od_config.photodiode_channel]."
        )

    return channel_angle_map


def _aggregate_angles(readings: structs.ODReadings) -> dict[pt.PdAngle, float]:
    by_angle: dict[pt.PdAngle, list[float]] = {}
    for reading in readings.ods.values():
        angle = cast(pt.PdAngle, reading.angle)
        if angle not in FUSION_ANGLES:
            continue
        by_angle.setdefault(angle, []).append(float(reading.od))

    return {angle: fmean(values) for angle, values in by_angle.items()}


def _measure_fusion_standard(
    od_value: float,
    rpm: float,
    samples_per_standard: int,
) -> list[dict[pt.PdAngle, float]]:
    from pioreactor.background_jobs.stirring import start_stirring as stirring

    channel_angle_map = _channel_angle_map_from_config()

    with stirring(
        target_rpm=rpm,
        unit=get_unit_name(),
        experiment=get_testing_experiment_name(),
    ) as st:
        st.block_until_rpm_is_close_to_target(abs_tolerance=120)

        with start_od_reading(
            config["od_config.photodiode_channel"],
            interval=None,
            unit=get_unit_name(),
            experiment=get_testing_experiment_name(),
            fake_data=is_testing_env(),
            calibration=False,
        ) as od_reader:
            for _ in range(3):
                od_reader.record_from_adc()

            samples: list[dict[pt.PdAngle, float]] = []
            for _ in range(samples_per_standard):
                od_readings = od_reader.record_from_adc()
                assert od_readings is not None
                samples.append(_aggregate_angles(od_readings))

    if not samples:
        raise ValueError(f"No readings captured for OD {od_value}.")
    return samples


def _measure_fusion_standard_for_session(
    ctx: SessionContext,
    od_value: float,
    rpm: float,
    samples_per_standard: int,
) -> list[dict[pt.PdAngle, float]]:
    if ctx.executor and ctx.mode == "ui":
        payload = ctx.executor(
            "od_fusion_standards_measure",
            {
                "od_value": od_value,
                "rpm": rpm,
                "samples_per_standard": samples_per_standard,
            },
        )
        raw_samples = payload.get("samples", [])
        if not isinstance(raw_samples, list):
            raise ValueError("Invalid fusion samples payload.")
        parsed: list[dict[pt.PdAngle, float]] = []
        for sample in raw_samples:
            if not isinstance(sample, dict):
                continue
            parsed.append({
                cast(pt.PdAngle, angle): float(value)
                for angle, value in sample.items()
                if angle in FUSION_ANGLES
            })
        return parsed
    return _measure_fusion_standard(od_value, rpm, samples_per_standard)


def _build_chart_metadata(records: list[tuple[pt.PdAngle, float, float]]) -> dict[str, object] | None:
    if not records:
        return None

    series: list[dict[str, object]] = []
    for angle in FUSION_ANGLES:
        points = [
            {"x": float(logc), "y": float(logy)}
            for ang, logc, logy in records
            if ang == angle
        ]
        if not points:
            continue
        series.append(
            {
                "id": angle,
                "label": f"{angle}°",
                "points": points,
            }
        )

    if not series:
        return None

    return {
        "title": "Fusion calibration progress",
        "x_label": "log10(OD600)",
        "y_label": "log(Voltage)",
        "series": series,
    }


def start_fusion_session() -> CalibrationSession:
    if config.get("od_reading.config", "ir_led_intensity") == "auto":
        raise ValueError(
            "ir_led_intensity cannot be auto for fusion calibration. Set a numeric value in config.ini."
        )

    if any(is_pio_job_running(["stirring", "od_reading"])):
        raise ValueError("Both stirring and OD reading must be off before starting.")

    _ensure_xr_model()
    channel_angle_map = _channel_angle_map_from_config()

    session_id = str(uuid.uuid4())
    return CalibrationSession(
        session_id=session_id,
        protocol_name=FusionStandardsODProtocol.protocol_name,
        target_device=pt.OD_FUSED_DEVICE,
        status="in_progress",
        step_id="intro",
        data={
            "channel_angle_map": to_builtins(channel_angle_map),
            "records": [],
            "od_values": [],
        },
        created_at=utc_iso_timestamp(),
        updated_at=utc_iso_timestamp(),
    )


class Intro(SessionStep):
    step_id = "intro"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        body = (
            "This protocol fits a fused OD model using the 45°, 90°, and 135° sensors. "
            "You will provide standards and collect multiple readings for each."
        )
        return steps.info("Fusion OD calibration", body)

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        return NameInput


class NameInput(SessionStep):
    step_id = "name"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Name this calibration",
            "Choose a unique name for this fused OD calibration.",
            [fields.str("calibration_name", label="Calibration name")],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        name = ctx.inputs.str("calibration_name")
        ctx.data["calibration_name"] = name

        if name in list_of_calibrations_by_device(pt.OD_FUSED_DEVICE):
            return NameOverwriteConfirm
        return RpmInput


class NameOverwriteConfirm(SessionStep):
    step_id = "name_overwrite"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        name = ctx.data.get("calibration_name", "")
        return steps.form(
            "Calibration already exists",
            f"A calibration named '{name}' already exists. Overwrite it?",
            [fields.bool("overwrite", label="Overwrite existing calibration?", default=False)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        overwrite = ctx.inputs.bool("overwrite")
        if not overwrite:
            return NameInput
        return RpmInput


class RpmInput(SessionStep):
    step_id = "rpm"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Set stirring speed",
            "Provide the RPM to use while measuring standards.",
            [fields.float("rpm", label="Stirring RPM", minimum=0.0, default=1800.0)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        ctx.data["rpm"] = ctx.inputs.float("rpm", minimum=0.0)
        return SamplesInput


class SamplesInput(SessionStep):
    step_id = "samples"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Samples per standard",
            "How many readings should we take per standard?",
            [
                fields.int(
                    "samples_per_standard",
                    label="Samples per standard",
                    minimum=MIN_SAMPLES_PER_STANDARD,
                    default=MIN_SAMPLES_PER_STANDARD,
                )
            ],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        ctx.data["samples_per_standard"] = ctx.inputs.int(
            "samples_per_standard", minimum=MIN_SAMPLES_PER_STANDARD
        )
        return PlaceStandard


class PlaceStandard(SessionStep):
    step_id = "place_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Place standard",
            "Enter the OD600 of the standard now in the vial.",
            [fields.float("od_value", label="OD600", minimum=0.0001)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        ctx.data["current_od_value"] = ctx.inputs.float("od_value", minimum=0.0001)
        return MeasureStandard


class MeasureStandard(SessionStep):
    step_id = "measure_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        od_value = ctx.data.get("current_od_value", "")
        step = steps.action(
            "Measure standard",
            f"Measuring OD600 {od_value}. Keep the vial in place.",
        )
        chart = _build_chart_metadata(ctx.data.get("records", []))
        if chart is not None:
            step.metadata = {"chart": chart}
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        od_value = float(ctx.data["current_od_value"])
        rpm = float(ctx.data["rpm"])
        samples_per_standard = int(ctx.data["samples_per_standard"])

        samples = _measure_fusion_standard_for_session(ctx, od_value, rpm, samples_per_standard)
        records = ctx.data.get("records", [])
        for sample in samples:
            for angle, reading in sample.items():
                records.append([angle, log10(od_value), log(max(reading, 1e-12))])

        ctx.data["records"] = records
        ctx.data.setdefault("od_values", []).append(od_value)
        return AnotherStandard


class AnotherStandard(SessionStep):
    step_id = "another_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.form(
            "Add another standard?",
            "Do you want to measure another OD600 standard?",
            [fields.bool("another", label="Measure another standard", default=True)],
        )
        chart = _build_chart_metadata(ctx.data.get("records", []))
        if chart is not None:
            step.metadata = {"chart": chart}
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        another = ctx.inputs.bool("another")
        if another:
            return PlaceStandard

        records = ctx.data.get("records", [])
        if not records:
            raise ValueError("No standards were measured.")

        fit = fit_fusion_model(
            [(angle, 10 ** logc, exp(logy)) for angle, logc, logy in records]
        )

        calibration = structs.ODFusionCalibration(
            created_at=current_utc_datetime(),
            calibrated_on_pioreactor_unit=get_unit_name(),
            calibration_name=str(ctx.data["calibration_name"]),
            curve_data_=fit.mu_splines["90"],
            curve_type="spline",
            recorded_data=fit.recorded_data,
            ir_led_intensity=float(config["od_reading.config"]["ir_led_intensity"]),
            angles=list(FUSION_ANGLES),
            mu_splines=fit.mu_splines,
            sigma_splines_log=fit.sigma_splines_log,
            min_logc=fit.min_logc,
            max_logc=fit.max_logc,
            sigma_floor=fit.sigma_floor,
        )

        ctx.session.result = {
            "calibration": to_builtins(calibration),
            "calibrations": [
                {
                    "device": pt.OD_FUSED_DEVICE,
                    "calibration_name": calibration.calibration_name,
                }
            ],
        }
        ctx.collected_calibrations.append(calibration)
        return CalibrationComplete


_FUSION_STEPS: StepRegistry = {
    Intro.step_id: Intro,
    NameInput.step_id: NameInput,
    NameOverwriteConfirm.step_id: NameOverwriteConfirm,
    RpmInput.step_id: RpmInput,
    SamplesInput.step_id: SamplesInput,
    PlaceStandard.step_id: PlaceStandard,
    MeasureStandard.step_id: MeasureStandard,
    AnotherStandard.step_id: AnotherStandard,
}


class FusionStandardsODProtocol(CalibrationProtocol[pt.ODFusedCalibrationDevice]):
    protocol_name = "od_fusion_standards"
    target_device: ClassVar[list[pt.ODFusedCalibrationDevice]] = [pt.OD_FUSED_DEVICE]
    title: ClassVar[str] = "OD fusion standards"
    description: ClassVar[str] = (
        "Fit a fused OD model using standards measured at 45°, 90°, and 135° sensors."
    )
    requirements: ClassVar[tuple[str, ...]] = (
        "Requires XR model with 45°, 90°, and 135° sensors configured.",
    )
    step_registry: ClassVar[StepRegistry] = _FUSION_STEPS

    @classmethod
    def start_session(cls, target_device: pt.ODFusedCalibrationDevice) -> CalibrationSession:
        if target_device != pt.OD_FUSED_DEVICE:
            raise ValueError("Invalid target device for fusion calibration.")
        return start_fusion_session()

    def run(self, target_device: pt.ODFusedCalibrationDevice, **kwargs) -> structs.ODFusionCalibration:
        _ensure_xr_model()
        raise ValueError("Use the calibration session flow for fusion calibration.")
