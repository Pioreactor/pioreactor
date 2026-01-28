# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from math import exp
from math import log
from math import log10
from statistics import fmean
from time import sleep
from typing import cast

from msgspec import to_builtins
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import start_od_reading
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
from pioreactor.estimators import list_of_estimators_by_device
from pioreactor.logging import create_logger
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.od_fusion import fit_fusion_model
from pioreactor.utils.od_fusion import FUSION_ANGLES
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_pioreactor_model
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


SAMPLES_PER_STANDARD = 4
logger = create_logger("calibrations.od_fusion_standards", experiment="$experiment")


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


def _measure_fusion_standard_samples(
    rpm: float,
    repeats: int = SAMPLES_PER_STANDARD,
) -> list[dict[pt.PdAngle, float]]:
    from pioreactor.background_jobs.stirring import start_stirring as stirring
    from itertools import cycle

    repeats = max(1, int(repeats))
    samples: list[dict[pt.PdAngle, float]] = []
    _jitter = cycle([0.9, 1.1, 0.8, 1.2])

    with stirring(
        target_rpm=rpm,
        unit=get_unit_name(),
        experiment=get_testing_experiment_name(),
    ) as st:
        st.block_until_rpm_is_close_to_target(abs_tolerance=60)

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
                sleep(1)

            for i in range(repeats):
                od_readings = od_reader.record_from_adc()
                st.set_target_rpm(rpm * next(_jitter))
                sleep(2)
                assert od_readings is not None
                samples.append(_aggregate_angles(od_readings))

    return samples


def _measure_fusion_standard_for_session(
    ctx: SessionContext,
    od_value: float,
    rpm: float,
    repeats: int = 1,
) -> list[dict[pt.PdAngle, float]]:
    if ctx.executor and ctx.mode == "ui":
        logger.debug(
            "Requesting fusion standard observation via executor: od_value=%s rpm=%s",
            od_value,
            rpm,
        )
        payload = ctx.executor(
            "od_fusion_standard_observation",
            {
                "od_value": od_value,
                "rpm": rpm,
                "repeats": repeats,
            },
        )
        logger.debug("Fusion observation payload type=%s payload=%r", type(payload).__name__, payload)

        samples: list[dict[pt.PdAngle, float]] = []
        for raw_sample in payload["samples"]:  # type: ignore
            if not isinstance(raw_sample, dict):
                continue
            samples.append(
                {
                    cast(pt.PdAngle, angle): float(value)
                    for angle, value in raw_sample.items()
                    if angle in FUSION_ANGLES
                }
            )
        if not samples:
            raise ValueError(
                "Fusion observation did not return sample data. Ensure the Huey consumer is running."
            )
        return samples
    return _measure_fusion_standard_samples(rpm, repeats=repeats)


def _build_chart_metadata(records: list[tuple[pt.PdAngle, float, float]]) -> dict[str, object] | None:
    if not records:
        return None

    series: list[dict[str, object]] = []
    for angle in FUSION_ANGLES:
        points = [{"x": float(logc), "y": float(logy)} for ang, logc, logy in records if ang == angle]
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
            "standards": [],
        },
        created_at=utc_iso_timestamp(),
        updated_at=utc_iso_timestamp(),
    )


class Intro(SessionStep):
    step_id = "intro"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.info(
            "Introduction",
            (
                "This protocol fits a OD model using fusing together 45°, 90°, and 135° signals into a single measurement."
                "You will need:\n\n"
                "1. A Pioreactor XR.\n"
                "2. At least four OD600 standards in Pioreactor vials, with stir bars.\n\n\u00a0\u00a0\u00a0\u00a0- It helps to number them 1, 2, ... N.\n\u00a0\u00a0\u00a0\u00a0- You don't need one of the standard vials to be a blank.\n"
            ),
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        return NameInput()


class NameInput(SessionStep):
    step_id = "name"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        default_name = ctx.data.get("default_name")
        if default_name is None:
            default_name = f"od-fused-estimator-{current_utc_datestamp()}"
            ctx.data["default_name"] = default_name
        return steps.form(
            "Name this estimator",
            "Choose a name for this fused OD estimator.",
            [fields.str("estimator_name", label="Estimator name", default=default_name)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        default_name = ctx.data.get("default_name")
        if default_name is None:
            default_name = f"od-fused-estimator-{current_utc_datestamp()}"
            ctx.data["default_name"] = default_name
        name = ctx.inputs.str("estimator_name", default=default_name)
        ctx.data["estimator_name"] = name

        if name in list_of_estimators_by_device(pt.OD_FUSED_DEVICE):
            return NameOverwriteConfirm()
        return RpmInput()


class NameOverwriteConfirm(SessionStep):
    step_id = "name_overwrite"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        name = ctx.data.get("estimator_name", "")
        return steps.form(
            "Estimator already exists",
            f"An estimator named '{name}' already exists. Overwrite it?",
            [fields.bool("overwrite", label="Overwrite existing estimator?", default=False)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        overwrite = ctx.inputs.bool("overwrite", default=False)
        if not overwrite:
            return NameInput()
        return RpmInput()


class RpmInput(SessionStep):
    step_id = "rpm"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Set stirring speed",
            "Provide the RPM to use while measuring standards.",
            [fields.float("rpm", label="Stirring RPM", minimum=0.0, default=500.0)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        ctx.data["rpm"] = ctx.inputs.float("rpm")
        return PlaceStandard()


class PlaceStandard(SessionStep):
    step_id = "place_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        standard_index = int(ctx.data.get("standard_index", 1))
        step = steps.action(
            f"Place standard vial {standard_index}",
            (f"Place standard vial {standard_index} with a stir bar into the Pioreactor. "),
        )
        step.metadata = {
            "image": {
                "src": "/static/svgs/place-standard-vial.svg",
                "alt": "Place a standard vial with a stir bar into the Pioreactor.",
                "caption": "Place a standard vial with a stir bar into the Pioreactor.",
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
        standard_index = int(ctx.data.get("standard_index", 1))
        step = steps.form(
            f"Record standard vial {standard_index}",
            f"Enter the OD600 measurement for standard vial {standard_index}.",
            [
                fields.float(
                    "od_value",
                    label="OD600",
                    minimum=0.0001,
                    min_error_msg="Don't use a blank in this protocol — we fit in log-space.",
                )
            ],
        )
        standards = ctx.data.get("standards", [])
        if isinstance(standards, list):
            rows = []
            for item in standards:
                if not isinstance(item, dict):
                    continue
                index = item.get("index")
                value = item.get("od_value")
                if isinstance(index, int) and isinstance(value, (int, float)):
                    rows.append([index, value])
            if rows:
                step.metadata = {
                    "table": {
                        "title": "Standards recorded so far",
                        "columns": ["#", "OD600"],
                        "rows": rows,
                    }
                }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        od_value = ctx.inputs.float("od_value")
        rpm = float(ctx.data["rpm"])

        ctx.data.setdefault("standard_index", 1)
        ctx.data["current_standard_od"] = od_value
        ctx.data["rpm"] = rpm
        return RecordObservation()


class RecordObservation(SessionStep):
    step_id = "record_observation"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        standard_index = int(ctx.data.get("standard_index", 1))
        step = steps.action(
            f"Recording standard vial {standard_index}",
            "Press Continue to start stirring and take OD readings for this standard.",
        )
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        od_value = float(ctx.data["current_standard_od"])
        standard_index = int(ctx.data.get("standard_index", 1))
        rpm = float(ctx.data["rpm"])

        samples = _measure_fusion_standard_for_session(
            ctx,
            od_value,
            rpm,
            repeats=SAMPLES_PER_STANDARD,
        )
        records = ctx.data.get("records", [])
        for sample in samples:
            for angle, reading in sample.items():
                records.append([angle, log10(od_value), log(max(reading, 1e-12))])

        ctx.data["records"] = records
        standards = ctx.data.get("standards", [])
        if not isinstance(standards, list):
            standards = []
        standards.append({"index": standard_index, "od_value": od_value})
        ctx.data["standards"] = standards
        return RemoveObservation()


class RemoveObservation(SessionStep):
    step_id = "remove_observation"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        standard_index = int(ctx.data.get("standard_index", 1))
        step = steps.action(
            f"Remove standard vial {standard_index}",
            "Remove the vial completely, then continue.",
        )
        step.metadata = {
            "image": {
                "src": "/static/svgs/remove-standard-vial.svg",
                "alt": "Remove the standard vial from the Pioreactor.",
                "caption": "Remove the standard vial completely.",
            }
        }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        return AnotherStandard()


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
        another = ctx.inputs.bool("another", default=True)
        if another:
            ctx.data["standard_index"] = int(ctx.data.get("standard_index", 1)) + 1
            return PlaceStandard()

        records = ctx.data.get("records", [])
        if not records:
            raise ValueError("No standards were measured.")

        fit = fit_fusion_model([(angle, 10**logc, exp(logy)) for angle, logc, logy in records])

        estimator = structs.ODFusionEstimator(
            created_at=current_utc_datetime(),
            calibrated_on_pioreactor_unit=get_unit_name(),
            estimator_name=str(ctx.data["estimator_name"]),
            recorded_data=fit.recorded_data,
            ir_led_intensity=float(config["od_reading.config"]["ir_led_intensity"]),
            angles=list(FUSION_ANGLES),
            mu_splines=fit.mu_splines,
            sigma_splines_log=fit.sigma_splines_log,
            min_logc=fit.min_logc,
            max_logc=fit.max_logc,
            sigma_floor=fit.sigma_floor,
        )

        result = ctx.store_estimator(estimator, pt.OD_FUSED_DEVICE)
        ctx.complete({"title": "Fusion estimator saved.", **result})
        return CalibrationComplete()


_FUSION_STEPS: StepRegistry = {
    Intro.step_id: Intro,
    NameInput.step_id: NameInput,
    NameOverwriteConfirm.step_id: NameOverwriteConfirm,
    RpmInput.step_id: RpmInput,
    PlaceStandard.step_id: PlaceStandard,
    MeasureStandard.step_id: MeasureStandard,
    RecordObservation.step_id: RecordObservation,
    RemoveObservation.step_id: RemoveObservation,
    AnotherStandard.step_id: AnotherStandard,
}


class FusionStandardsODProtocol(CalibrationProtocol[pt.ODFusedCalibrationDevice]):
    protocol_name = "od_fusion_standards"
    target_device = [cast(pt.ODFusedCalibrationDevice, pt.OD_FUSED_DEVICE)]
    title = "Fusion OD using standards"
    description = "Fit an OD model by fusing the 45°, 90°, and 135° sensor readings into a single measurement"
    requirements = (
        "Requires XR model with 45°, 90°, and 135° sensors.",
        "At least four vials containing standards with known OD value",
        "Stir bars",
    )
    step_registry = _FUSION_STEPS
    priority = 1

    @classmethod
    def start_session(cls, target_device: pt.ODFusedCalibrationDevice) -> CalibrationSession:
        if target_device != pt.OD_FUSED_DEVICE:
            raise ValueError("Invalid target device for fusion calibration.")
        return start_fusion_session()

    def run(
        self, target_device: pt.ODFusedCalibrationDevice
    ) -> structs.CalibrationBase | list[structs.CalibrationBase]:
        _ensure_xr_model()
        raise ValueError("Use the calibration session flow for fusion calibration.")
