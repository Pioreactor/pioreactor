# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from math import log10
from typing import cast

from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.calibrations.protocols.od_fusion_standards import _channel_angle_map_from_config
from pioreactor.calibrations.protocols.od_fusion_standards import _ensure_xr_model
from pioreactor.calibrations.protocols.od_fusion_standards import _measure_fusion_standard_for_session
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
from pioreactor.cluster_management import get_workers_in_inventory
from pioreactor.config import config
from pioreactor.estimators import list_of_estimators_by_device
from pioreactor.estimators import load_estimator
from pioreactor.logging import create_logger
from pioreactor.pubsub import get_from
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.od_fusion import compute_fused_od
from pioreactor.utils.od_fusion import FUSION_ANGLES
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_unit_name


ESTIMATOR_DEVICE = pt.OD_FUSED_DEVICE
logger = create_logger("calibrations.od_fusion_offset", experiment="$experiment")


def _default_estimator_name(source_name: str | None) -> str:
    suffix = current_utc_datestamp()
    if source_name:
        return f"{source_name}-offset-{suffix}"
    return f"od-fused-offset-{suffix}"


def _ordered_worker_options() -> list[str]:
    units: list[str] = []
    try:
        units = list(get_workers_in_inventory())
    except Exception:
        units = []
    current = get_unit_name()
    unique_units = {current, *units}
    ordered = [current]
    ordered.extend(sorted(unit for unit in unique_units if unit != current))
    return ordered


def _list_estimators_for_worker(worker: str) -> tuple[list[str], str | None]:
    try:
        if worker == get_unit_name():
            estimators = list_of_estimators_by_device(ESTIMATOR_DEVICE)
            return sorted(estimators), None

        response = get_from(worker, f"/unit_api/estimators/{ESTIMATOR_DEVICE}")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return [], f"Unexpected estimator list payload from {worker}."

        names: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = item.get("estimator_name")
            if isinstance(name, str):
                names.append(name)
        return sorted(set(names)), None
    except Exception as exc:
        return [], str(exc)


def _load_estimator_for_worker(worker: str, estimator_name: str) -> structs.ODFusionEstimator:
    if worker == get_unit_name():
        return load_estimator(ESTIMATOR_DEVICE, estimator_name)

    response = get_from(worker, f"/unit_api/estimators/{ESTIMATOR_DEVICE}/{estimator_name}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected estimator payload from {worker}.")

    payload.pop("is_active", None)
    payload.pop("pioreactor_unit", None)
    return json_decode(json_encode(payload), type=structs.ODFusionEstimator)


def _shift_spline_fit_data(spline_data: structs.SplineFitData, offset_logc: float) -> structs.SplineFitData:
    return structs.SplineFitData(
        knots=[float(knot + offset_logc) for knot in spline_data.knots],
        coefficients=[list(map(float, coeffs)) for coeffs in spline_data.coefficients],
    )


def _apply_logc_offset_to_estimator(
    estimator: structs.ODFusionEstimator,
    *,
    estimator_name: str,
    calibrated_on_unit: str,
    offset_logc: float,
    standard_od: float,
    estimated_od: float,
    source_unit: str,
    source_estimator_name: str,
    observation: dict[pt.PdAngle, float],
) -> structs.ODFusionEstimator:
    mu_splines = {
        angle: _shift_spline_fit_data(estimator.mu_splines[angle], offset_logc) for angle in estimator.angles
    }
    sigma_splines_log = {
        angle: _shift_spline_fit_data(estimator.sigma_splines_log[angle], offset_logc)
        for angle in estimator.angles
    }

    recorded_data = {
        "new_observation": {str(angle): float(value) for angle, value in observation.items()},
        "by_angle": estimator.recorded_data,
    }

    return structs.ODFusionEstimator(
        created_at=current_utc_datetime(),
        calibrated_on_pioreactor_unit=calibrated_on_unit,
        estimator_name=estimator_name,
        recorded_data=recorded_data,
        ir_led_intensity=float(config["od_reading.config"]["ir_led_intensity"]),
        angles=list(estimator.angles),
        mu_splines=mu_splines,
        sigma_splines_log=sigma_splines_log,
        min_logc=float(estimator.min_logc + offset_logc),
        max_logc=float(estimator.max_logc + offset_logc),
        sigma_floor=float(estimator.sigma_floor),
    )


def start_fusion_offset_session() -> CalibrationSession:
    if config.get("od_reading.config", "ir_led_intensity") == "auto":
        raise ValueError(
            "ir_led_intensity cannot be auto for fusion offset calibration. Set a numeric value in config.ini."
        )

    if any(is_pio_job_running(["stirring", "od_reading"])):
        raise ValueError("Both stirring and OD reading must be off before starting.")

    _ensure_xr_model()
    _channel_angle_map_from_config()

    session_id = str(uuid.uuid4())
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id=session_id,
        protocol_name=FusionOffsetODProtocol.protocol_name,
        target_device=ESTIMATOR_DEVICE,
        status="in_progress",
        step_id="intro",
        data={
            "source_unit": get_unit_name(),
            "rpm": config.getfloat("stirring.config", "initial_target_rpm", fallback=500.0),
        },
        created_at=now,
        updated_at=now,
    )


class Intro(SessionStep):
    step_id = "intro"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.info(
            "Fusion OD single-point offset",
            (
                "This protocol adjusts an existing fused OD estimator using a single OD600 standard. "
                "You will need:\n"
                "1. A Pioreactor XR.\n"
                "2. An existing od_fused estimator on any worker.\n"
                "3. One OD600 standard vial with a stir bar.\n\n"
                "For best results, choose a standard near the regime you most care about (high, medium, or low density, etc.)"
            ),
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        return SelectWorker()


class SelectWorker(SessionStep):
    step_id = "select_worker"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        options = _ordered_worker_options()
        default_unit = ctx.data.get("source_unit", get_unit_name())
        if default_unit not in options and options:
            default_unit = options[0]
        return steps.form(
            "Choose estimator source",
            "Select the worker that hosts the existing od_fused estimator.",
            [fields.choice("source_unit", options=options, label="Source worker", default=default_unit)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        options = _ordered_worker_options()
        default_unit = ctx.data.get("source_unit", get_unit_name())
        selected = ctx.inputs.choice("source_unit", options, default=default_unit)
        ctx.data["source_unit"] = selected
        return SelectEstimator()


class SelectEstimator(SessionStep):
    step_id = "select_estimator"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        source_unit = str(ctx.data.get("source_unit", get_unit_name()))
        estimators, error = _list_estimators_for_worker(source_unit)
        if error:
            return steps.info(
                "Unable to load estimators",
                f"Could not load od_fused estimators from {source_unit}: {error}",
            )
        if not estimators:
            return steps.info(
                "No estimators found",
                f"No od_fused estimators were found on {source_unit}. Choose another worker or create one first.",
            )

        default_name = estimators[0]
        return steps.form(
            "Choose estimator",
            f"Select the estimator from {source_unit} to offset.",
            [
                fields.choice(
                    "source_estimator_name",
                    options=estimators,
                    label="Source estimator",
                    default=default_name,
                )
            ],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        source_unit = str(ctx.data.get("source_unit", get_unit_name()))
        estimators, error = _list_estimators_for_worker(source_unit)
        if error or not estimators:
            return SelectWorker()
        default_name = estimators[0]
        selected = ctx.inputs.choice("source_estimator_name", estimators, default=default_name)
        ctx.data["source_estimator_name"] = selected
        return NameInput()


class NameInput(SessionStep):
    step_id = "name"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        source_name = ctx.data.get("source_estimator_name")
        default_name = ctx.data.get("default_name")
        if not isinstance(default_name, str):
            default_name = _default_estimator_name(str(source_name) if source_name else None)
            ctx.data["default_name"] = default_name
        return steps.form(
            "Name this estimator",
            "Choose a name for the offset fused OD estimator.",
            [fields.str("estimator_name", label="Estimator name", default=default_name)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        default_name = ctx.data.get("default_name")
        if not isinstance(default_name, str):
            default_name = _default_estimator_name(ctx.data.get("source_estimator_name"))
            ctx.data["default_name"] = default_name
        name = ctx.inputs.str("estimator_name", default=default_name)
        ctx.data["estimator_name"] = name

        if name in list_of_estimators_by_device(ESTIMATOR_DEVICE):
            return NameOverwriteConfirm()
        return RpmInput()


class NameOverwriteConfirm(SessionStep):
    step_id = "name_overwrite"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        name = ctx.data.get("estimator_name", "")
        return steps.form(
            "Estimator already exists",
            f"An estimator named '{name}' already exists on this Pioreactor. Overwrite it?",
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
        default_rpm = float(ctx.data.get("rpm", 500.0))
        return steps.form(
            "Stirring setup",
            "Optional: set stirring RPM used during the reading.",
            [fields.float("rpm", label="Stirring RPM", default=default_rpm, minimum=0.0)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        default_rpm = float(ctx.data.get("rpm", 500.0))
        rpm = ctx.inputs.float("rpm", minimum=0.0, default=default_rpm)
        ctx.data["rpm"] = rpm
        return PlaceStandard()


class PlaceStandard(SessionStep):
    step_id = "place_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.action(
            "Insert standard vial",
            "Place the OD600 standard vial with a stir bar into the Pioreactor.",
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
            return StandardOdInput()
        return None


class StandardOdInput(SessionStep):
    step_id = "standard_od"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.form(
            "Enter standard OD",
            "Enter the OD600 value for the standard vial.",
            [fields.float("standard_od", label="OD600", minimum=1e-6)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        ctx.data["standard_od"] = ctx.inputs.float("standard_od", minimum=1e-6)
        return RecordObservation()


class RecordObservation(SessionStep):
    step_id = "record_observation"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.action(
            "Record OD reading",
            "Press Continue to take an OD reading for the standard vial.",
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        source_unit = str(ctx.data.get("source_unit", get_unit_name()))
        source_estimator_name = str(ctx.data["source_estimator_name"])
        estimator_name = str(ctx.data["estimator_name"])
        standard_od = float(ctx.data["standard_od"])
        rpm = float(ctx.data["rpm"])

        base_estimator = _load_estimator_for_worker(source_unit, source_estimator_name)
        if set(base_estimator.angles) != set(FUSION_ANGLES):
            raise ValueError("Selected estimator angles do not match fusion angles.")

        logger.debug(
            "Taking fusion offset observation: source_unit=%s estimator=%s standard_od=%s rpm=%s",
            source_unit,
            source_estimator_name,
            standard_od,
            rpm,
        )
        samples = _measure_fusion_standard_for_session(ctx, standard_od, rpm, repeats=1)
        sample = samples[0]
        logger.debug("Fusion offset observation sample keys=%s", sorted(sample.keys()))
        for angle in base_estimator.angles:
            if angle not in sample:
                raise ValueError(f"Missing fusion reading for angle {angle}.")

        estimated_od = compute_fused_od(base_estimator, sample)
        if estimated_od <= 0 or standard_od <= 0:
            raise ValueError("OD values must be positive to compute offset.")

        offset_logc = log10(standard_od) - log10(estimated_od)

        new_estimator = _apply_logc_offset_to_estimator(
            base_estimator,
            estimator_name=estimator_name,
            calibrated_on_unit=get_unit_name(),
            offset_logc=offset_logc,
            standard_od=standard_od,
            estimated_od=estimated_od,
            source_unit=source_unit,
            source_estimator_name=source_estimator_name,
            observation=sample,
        )

        result = ctx.store_estimator(new_estimator, ESTIMATOR_DEVICE)
        ctx.complete(
            {
                "title": "Fusion estimator saved.",
                **result,
                "source_unit": source_unit,
                "source_estimator": source_estimator_name,
                "standard_od": float(standard_od),
                "estimated_od": float(estimated_od),
                "offset_logc": float(offset_logc),
            }
        )
        return CalibrationComplete()


_FUSION_OFFSET_STEPS: StepRegistry = {
    Intro.step_id: Intro,
    SelectWorker.step_id: SelectWorker,
    SelectEstimator.step_id: SelectEstimator,
    NameInput.step_id: NameInput,
    NameOverwriteConfirm.step_id: NameOverwriteConfirm,
    RpmInput.step_id: RpmInput,
    PlaceStandard.step_id: PlaceStandard,
    StandardOdInput.step_id: StandardOdInput,
    RecordObservation.step_id: RecordObservation,
}


class FusionOffsetODProtocol(CalibrationProtocol[pt.ODFusedCalibrationDevice]):
    protocol_name = "od_fusion_offset"
    target_device = [cast(pt.ODFusedCalibrationDevice, ESTIMATOR_DEVICE)]
    title = "Fusion OD single-point offset"
    description = "Adjust an existing fused OD estimator using a single OD600 standard."
    requirements = (
        "Requires XR model with 45°, 90°, and 135° sensors.",
        "An existing od_fused estimator.",
        "One OD600 standard vial with a stir bar.",
    )
    step_registry = _FUSION_OFFSET_STEPS
    priority = 2

    @classmethod
    def start_session(cls, target_device: pt.ODFusedCalibrationDevice) -> CalibrationSession:
        if target_device != ESTIMATOR_DEVICE:
            raise ValueError("Invalid target device for fusion offset calibration.")
        return start_fusion_offset_session()

    def run(
        self, target_device: pt.ODFusedCalibrationDevice
    ) -> structs.CalibrationBase | list[structs.CalibrationBase]:
        _ensure_xr_model()
        raise ValueError("Use the calibration session flow for fusion offset calibration.")
