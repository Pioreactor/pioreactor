# -*- coding: utf-8 -*-
import uuid
from time import sleep
from typing import cast
from typing import ClassVar

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import average_over_od_readings
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.calibrations import utils as calibration_utils
from pioreactor.calibrations.registry import CalibrationProtocol
from pioreactor.calibrations.session_flow import advance_session
from pioreactor.calibrations.session_flow import CalibrationComplete
from pioreactor.calibrations.session_flow import get_session_step
from pioreactor.calibrations.session_flow import run_session_in_cli
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionExecutor
from pioreactor.calibrations.session_flow import SessionStep
from pioreactor.calibrations.session_flow import StepRegistry
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


STANDARD_OD = 1.0
DEFAULT_TARGET_ANGLES = {"45", "90", "135"}


def get_ir_led_intensity() -> float:
    ir_intensity_setting = config.get("od_reading.config", "ir_led_intensity")
    if ir_intensity_setting == "auto":
        raise ValueError(
            "ir_led_intensity must be numeric when creating OD calibrations from the optical reference standard. Try 80."
        )
    return float(ir_intensity_setting)


def get_channel_angle_map(
    target_device: pt.ODCalibrationDevices,
) -> dict[pt.PdChannel, pt.PdAngle]:
    pd_channels = config["od_config.photodiode_channel"]
    channel_angle_map: dict[pt.PdChannel, pt.PdAngle] = {}

    for channel, angle in pd_channels.items():
        if angle in (None, "", REF_keyword):
            continue
        channel_angle_map[cast(pt.PdChannel, channel)] = cast(pt.PdAngle, angle)

    if target_device != "od":
        target_angle = target_device.removeprefix("od")
        channel_angle_map = {
            channel: angle for channel, angle in channel_angle_map.items() if angle == target_angle
        }
    else:
        channel_angle_map = {
            channel: angle for channel, angle in channel_angle_map.items() if angle in DEFAULT_TARGET_ANGLES
        }

    if not channel_angle_map:
        raise ValueError("No configured PD channels match the selected device.")

    return channel_angle_map


def record_reference_standard(ir_led_intensity: float) -> structs.ODReadings:
    logger = create_logger(
        "od_reference_standard",
        unit=get_unit_name(),
        experiment=get_testing_experiment_name(),
    )
    logger.info("Recording OD readings...")
    with start_od_reading(
        config["od_config.photodiode_channel"],
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_testing_experiment_name(),
        calibration=False,
        ir_led_intensity=ir_led_intensity,
    ) as od_reader:
        for _ in range(2):
            sleep(1.0 / config.getfloat("od_reading.config", "samples_per_second"))
            od_reader.record_from_adc()

        od_readings_samples: list[structs.ODReadings] = []
        for _ in range(5):
            od_readings = od_reader.record_from_adc()
            assert od_readings is not None
            sleep(1.0 / config.getfloat("od_reading.config", "samples_per_second"))
            od_readings_samples.append(od_readings)

    averaged_od_readings = average_over_od_readings(*od_readings_samples)
    averaged_od_summary = ", ".join(
        f"channel {pd_channel} ({od_reading.angle} deg)={od_reading.od:.6f}"
        for pd_channel, od_reading in sorted(averaged_od_readings.ods.items())
    )
    logger.info("Averaged OD readings: %s", averaged_od_summary)
    return averaged_od_readings


def _record_reference_standard_for_session(
    ctx: SessionContext,
    ir_led_intensity: float,
) -> dict[str, dict[str, float]] | structs.ODReadings:
    if ctx.executor and ctx.mode == "ui":
        payload = ctx.executor(
            "od_reference_standard_read",
            {"ir_led_intensity": ir_led_intensity},
        )
        raw = payload.get("od_readings", {})
        if not isinstance(raw, dict):
            raise ValueError("Invalid OD readings payload.")
        return raw
    return record_reference_standard(ir_led_intensity)


def start_reference_standard_session(
    target_device: pt.ODCalibrationDevices,
) -> CalibrationSession:
    session_id = str(uuid.uuid4())
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id=session_id,
        protocol_name=ODReferenceStandardProtocol.protocol_name,
        target_device=target_device,
        status="in_progress",
        step_id="intro",
        data={},
        created_at=now,
        updated_at=now,
    )


class Intro(SessionStep):
    step_id = "intro"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.info(
            "OD reference standard calibration",
            (
                "This routine creates OD calibrations using the optical reference standard. "
                "Ensure the jig is installed, OD reading is stopped, and ir_led_intensity is numeric."
            ),
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return RecordReadings()
        return None


class RecordReadings(SessionStep):
    step_id = "record_readings"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.action(
            "Record reference standard",
            "Continue to record OD readings against the optical reference standard.",
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if is_pio_job_running("od_reading"):
            raise ValueError("OD reading should be turned off.")

        ir_led_intensity = get_ir_led_intensity()
        channel_angle_map = get_channel_angle_map(cast(pt.ODCalibrationDevices, ctx.session.target_device))

        od_readings = _record_reference_standard_for_session(ctx, ir_led_intensity)
        recorded_ods = [0.0, 1000 * STANDARD_OD]
        timestamp = current_utc_datetime().strftime("%Y-%m-%d_%H-%M")

        calibration_links: list[dict[str, str | None]] = []
        if isinstance(od_readings, dict):
            for raw_channel, od_reading_payload in od_readings.items():
                pd_channel = cast(pt.PdChannel, raw_channel)
                if pd_channel not in channel_angle_map:
                    continue
                angle = channel_angle_map[pd_channel]
                od_value = float(od_reading_payload["od"])

                recorded_voltages = [0.0, 1000 * od_value]
                curve_data_ = calibration_utils.calculate_poly_curve_of_best_fit(
                    recorded_ods, recorded_voltages, degree=1
                )
                calibration = structs.ODCalibration(
                    created_at=current_utc_datetime(),
                    calibrated_on_pioreactor_unit=get_unit_name(),
                    calibration_name=f"od{angle}-optics-calibration-jig-{timestamp}",
                    angle=angle,
                    curve_data_=curve_data_,
                    curve_type="poly",
                    recorded_data={"x": recorded_ods, "y": recorded_voltages},
                    ir_led_intensity=ir_led_intensity,
                    pd_channel=pd_channel,
                )
                calibration_links.append(ctx.store_calibration(calibration, f"od{angle}"))
        else:
            for raw_channel, od_reading_struct in od_readings.ods.items():
                pd_channel = cast(pt.PdChannel, raw_channel)
                if pd_channel not in channel_angle_map:
                    continue
                angle = channel_angle_map[pd_channel]
                od_value = float(od_reading_struct.od)

                recorded_voltages = [0.0, 1000 * od_value]
                curve_data_ = calibration_utils.calculate_poly_curve_of_best_fit(
                    recorded_ods, recorded_voltages, degree=1
                )
                calibration = structs.ODCalibration(
                    created_at=current_utc_datetime(),
                    calibrated_on_pioreactor_unit=get_unit_name(),
                    calibration_name=f"od{angle}-optical-reference-standard-{timestamp}",
                    angle=angle,
                    curve_data_=curve_data_,
                    curve_type="poly",
                    recorded_data={"x": recorded_ods, "y": recorded_voltages},
                    ir_led_intensity=ir_led_intensity,
                    pd_channel=pd_channel,
                )
                calibration_links.append(ctx.store_calibration(calibration, f"od{angle}"))

        if not calibration_links:
            raise ValueError("No matching channels were recorded for this calibration.")

        ctx.complete({"calibrations": calibration_links})
        return CalibrationComplete()


_REFERENCE_STANDARD_STEPS: StepRegistry = {
    Intro.step_id: Intro,
    RecordReadings.step_id: RecordReadings,
}


def advance_reference_standard_session(
    session: CalibrationSession,
    inputs: dict[str, object],
    executor: SessionExecutor | None = None,
) -> CalibrationSession:
    return advance_session(_REFERENCE_STANDARD_STEPS, session, inputs, executor)


def get_reference_standard_step(
    session: CalibrationSession, executor: SessionExecutor | None = None
) -> CalibrationStep | None:
    return get_session_step(_REFERENCE_STANDARD_STEPS, session, executor)


class ODReferenceStandardProtocol(CalibrationProtocol[pt.ODCalibrationDevices]):
    target_device = pt.OD_DEVICES
    protocol_name = "od_reference_standard"
    title = "Optics calibration jig"
    description = "Calibrate OD using the Pioreactor Optics calibration jig."
    requirements = ("Optics calibration jig", "2x stainless steel ports from the Vial Cap S")
    step_registry: ClassVar[StepRegistry] = _REFERENCE_STANDARD_STEPS

    @classmethod
    def start_session(cls, target_device: pt.ODCalibrationDevices) -> CalibrationSession:
        return start_reference_standard_session(target_device)

    def run(  # type: ignore
        self, target_device: pt.ODCalibrationDevices, *args, **kwargs
    ) -> list[structs.ODCalibration]:
        session = start_reference_standard_session(target_device)
        return run_session_in_cli(_REFERENCE_STANDARD_STEPS, session)
