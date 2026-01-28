# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from math import log10
from statistics import fmean
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
STANDARDS_REQUIRED = 2
SAMPLES_PER_STANDARD = 4
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


def _affine_transform_cubic_fit_data(
    curve_data: structs.AkimaFitData,
    scale_logc: float,
    offset_logc: float,
) -> structs.AkimaFitData:
    if scale_logc <= 0:
        raise ValueError("Scale must be positive to transform curve data.")

    knots = [float(scale_logc * knot + offset_logc) for knot in curve_data.knots]
    coefficients = [
        [
            float(coeffs[0]),
            float(coeffs[1] / scale_logc),
            float(coeffs[2] / scale_logc**2),
            float(coeffs[3] / scale_logc**3),
        ]
        for coeffs in curve_data.coefficients
    ]

    return structs.AkimaFitData(knots=knots, coefficients=coefficients)


def _apply_logc_affine_to_estimator(
    estimator: structs.ODFusionEstimator,
    *,
    estimator_name: str,
    calibrated_on_unit: str,
    scale_logc: float,
    offset_logc: float,
    standards: list[dict[str, object]],
    source_unit: str,
    source_estimator_name: str,
) -> structs.ODFusionEstimator:
    mu_splines = {
        angle: _affine_transform_cubic_fit_data(estimator.mu_splines[angle], scale_logc, offset_logc)
        for angle in estimator.angles
    }
    sigma_splines_log = {
        angle: _affine_transform_cubic_fit_data(estimator.sigma_splines_log[angle], scale_logc, offset_logc)
        for angle in estimator.angles
    }

    recorded_data = {
        "transform": {
            "type": "logc_affine",
            "scale_logc": float(scale_logc),
            "offset_logc": float(offset_logc),
            "source_unit": source_unit,
            "source_estimator_name": source_estimator_name,
            "source_ir_led_intensity": float(estimator.ir_led_intensity),
        },
        "standards": standards,
        "base_recorded_data": estimator.recorded_data,
    }

    min_logc = float(estimator.min_logc * scale_logc + offset_logc)
    max_logc = float(estimator.max_logc * scale_logc + offset_logc)

    return structs.ODFusionEstimator(
        created_at=current_utc_datetime(),
        calibrated_on_pioreactor_unit=calibrated_on_unit,
        estimator_name=estimator_name,
        recorded_data=recorded_data,
        ir_led_intensity=float(config["od_reading.config"]["ir_led_intensity"]),
        angles=list(estimator.angles),
        mu_splines=mu_splines,
        sigma_splines_log=sigma_splines_log,
        min_logc=min_logc,
        max_logc=max_logc,
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
            "Fusion OD two-point offset",
            (
                "This protocol adjusts an existing fused OD estimator using two OD standards. "
                "You will need:\n"
                "1. A Pioreactor XR.\n"
                "2. An existing od_fused estimator on any worker.\n"
                "3. Two standard vials of known OD with stir bars.\n\n"
                "For best results, choose standards that bracket the regime you care about and stay within "
                "a locally monotonic region (i.e. not beyond the saturation point)."
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
        rpm = ctx.inputs.float("rpm")
        ctx.data["rpm"] = rpm
        ctx.data["standard_index"] = 1
        ctx.data["standards"] = []
        return PlaceStandard()


class PlaceStandard(SessionStep):
    step_id = "place_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        standard_index = int(ctx.data.get("standard_index", 1))
        step = steps.action(
            f"Insert standard vial {standard_index} of {STANDARDS_REQUIRED}",
            f"Place standard vial {standard_index} with a stir bar into the Pioreactor.",
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
        standard_index = int(ctx.data.get("standard_index", 1))
        return steps.form(
            f"Enter OD for standard {standard_index} of {STANDARDS_REQUIRED}",
            "Enter the OD value for the standard vial.",
            [fields.float("standard_od", label="OD", minimum=1e-6)],
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        ctx.data["standard_od"] = ctx.inputs.float("standard_od")
        return RecordObservation()


class RecordObservation(SessionStep):
    step_id = "record_observation"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        standard_index = int(ctx.data.get("standard_index", 1))
        return steps.action(
            f"Record OD reading for standard {standard_index} of {STANDARDS_REQUIRED}",
            "Press Continue to take OD readings for the standard vial.",
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        source_unit = str(ctx.data.get("source_unit", get_unit_name()))
        source_estimator_name = str(ctx.data["source_estimator_name"])
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
        samples = _measure_fusion_standard_for_session(
            ctx,
            standard_od,
            rpm,
            repeats=SAMPLES_PER_STANDARD,
        )
        for sample in samples:
            logger.debug("Fusion offset observation sample keys=%s", sorted(sample.keys()))
            for angle in base_estimator.angles:
                if angle not in sample:
                    raise ValueError(f"Missing fusion reading for angle {angle}.")

        estimated_ods = [compute_fused_od(base_estimator, sample) for sample in samples]
        estimated_od = fmean(estimated_ods)
        if estimated_od <= 0 or standard_od <= 0:
            raise ValueError("OD values must be positive to compute offset.")

        standards = ctx.data.get("standards", [])
        if not isinstance(standards, list):
            standards = []
        standards.append(
            {
                "standard_od": float(standard_od),
                "estimated_od": float(estimated_od),
                "estimated_ods": [float(value) for value in estimated_ods],
                "observations": samples,
            }
        )
        ctx.data["standards"] = standards
        return RemoveStandard()


class RemoveStandard(SessionStep):
    step_id = "remove_standard"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        standard_index = int(ctx.data.get("standard_index", 1))
        step = steps.action(
            f"Remove standard vial {standard_index} of {STANDARDS_REQUIRED}",
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
        standard_index = int(ctx.data.get("standard_index", 1))
        if standard_index < STANDARDS_REQUIRED:
            ctx.data["standard_index"] = standard_index + 1
            return PlaceStandard()

        standards = ctx.data.get("standards", [])
        if not isinstance(standards, list) or len(standards) != STANDARDS_REQUIRED:
            raise ValueError("Expected two standards to compute affine correction.")

        source_unit = str(ctx.data.get("source_unit", get_unit_name()))
        source_estimator_name = str(ctx.data["source_estimator_name"])
        estimator_name = str(ctx.data["estimator_name"])

        base_estimator = _load_estimator_for_worker(source_unit, source_estimator_name)
        if set(base_estimator.angles) != set(FUSION_ANGLES):
            raise ValueError("Selected estimator angles do not match fusion angles.")

        od_true_1 = float(standards[0]["standard_od"])
        od_true_2 = float(standards[1]["standard_od"])
        od_est_1 = float(standards[0]["estimated_od"])
        od_est_2 = float(standards[1]["estimated_od"])

        log_true_1 = log10(od_true_1)
        log_true_2 = log10(od_true_2)
        log_est_1 = log10(od_est_1)
        log_est_2 = log10(od_est_2)

        if log_est_2 == log_est_1:
            raise ValueError("Estimated OD values are identical; cannot fit affine correction.")

        scale_logc = (log_true_2 - log_true_1) / (log_est_2 - log_est_1)
        if scale_logc <= 0:
            raise ValueError(
                "Affine correction produced a non-positive scale. "
                "Choose two standards within a locally monotonic region."
            )

        offset_logc = log_true_1 - scale_logc * log_est_1

        new_estimator = _apply_logc_affine_to_estimator(
            base_estimator,
            estimator_name=estimator_name,
            calibrated_on_unit=get_unit_name(),
            scale_logc=scale_logc,
            offset_logc=offset_logc,
            standards=standards,
            source_unit=source_unit,
            source_estimator_name=source_estimator_name,
        )

        result = ctx.store_estimator(new_estimator, ESTIMATOR_DEVICE)
        ctx.complete(
            {
                "title": "Fusion estimator saved.",
                **result,
                "source_unit": source_unit,
                "source_estimator": source_estimator_name,
                "scale_logc": float(scale_logc),
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
    RemoveStandard.step_id: RemoveStandard,
}


class FusionOffsetODProtocol(CalibrationProtocol[pt.ODFusedCalibrationDevice]):
    protocol_name = "od_fusion_offset"
    target_device = [cast(pt.ODFusedCalibrationDevice, ESTIMATOR_DEVICE)]
    title = "Fusion OD two-point offset"
    description = "Adjust an existing fused OD estimator using two OD standards."
    requirements = (
        "Requires XR model with 45°, 90°, and 135° sensors.",
        "An existing od_fused estimator.",
        "Two standard vials of known OD with stir bars.",
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
