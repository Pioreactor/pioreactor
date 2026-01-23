# -*- coding: utf-8 -*-
"""
maps DC -> RPM, and PID will correct any disturbances
This should be run with a vial in, with a stirbar. Water is fine.

"""
import uuid
from time import sleep
from typing import ClassVar
from typing import Literal

from pioreactor.background_jobs import stirring
from pioreactor.calibrations.registry import CalibrationProtocol
from pioreactor.calibrations.session_flow import CalibrationComplete
from pioreactor.calibrations.session_flow import run_session_in_cli
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionStep
from pioreactor.calibrations.session_flow import StepRegistry
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.calibrations.utils import linspace
from pioreactor.config import config
from pioreactor.exc import JobPresentError
from pioreactor.hardware import voltage_in_aux
from pioreactor.logging import create_logger
from pioreactor.structs import SimpleStirringCalibration
from pioreactor.utils import clamp
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import managed_lifecycle
from pioreactor.utils.math_helpers import simple_linear_regression
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name


def _resolve_dc_bounds(min_dc: float | None, max_dc: float | None) -> tuple[float, float]:
    if max_dc is None and min_dc is None:
        # seed with initial_duty_cycle
        config_initial_duty_cycle = config.getfloat("stirring.config", "initial_duty_cycle", fallback=30)
        min_dc = config_initial_duty_cycle * 0.66
        max_dc = clamp(0, config_initial_duty_cycle * 1.33, 100)
    elif (max_dc is None) or (min_dc is None):
        raise ValueError("min_dc and max_dc must both be set.")
    return min_dc, max_dc


def collect_stirring_measurements(
    min_dc: float | None = None, max_dc: float | None = None
) -> tuple[list[float], list[float]]:
    min_dc, max_dc = _resolve_dc_bounds(min_dc, max_dc)
    unit = get_unit_name()
    experiment = get_testing_experiment_name()
    action_name = "stirring_calibration"
    logger = create_logger(action_name, experiment="$experiment")

    with managed_lifecycle(unit, experiment, action_name) as lc:
        logger.info("Starting stirring calibration.")

        if is_pio_job_running("stirring"):
            logger.error("Make sure Stirring job is off before running stirring calibration. Exiting.")
            raise JobPresentError("Make sure Stirring job is off before running stirring calibration.")

        measured_rpms: list[float] = []

        # go up and down to observe any hysteresis.
        dcs = linspace(max_dc, min_dc, 5) + linspace(min_dc, max_dc, 5) + linspace(max_dc, min_dc, 5)
        n_samples = len(dcs)

        with stirring.RpmFromFrequency() as rpm_calc, stirring.Stirrer(
            target_rpm=0,
            unit=unit,
            experiment=experiment,
            rpm_calculator=None,
            calibration=False,
            enable_dodging_od=False,
        ) as st:
            rpm_calc.setup()
            st.duty_cycle = (
                max_dc + min_dc
            ) / 2  # we start with a somewhat low value, s.t. the stir bar is caught.
            st.start_stirring()
            sleep(3)

            for count, dc in enumerate(dcs, start=1):
                st.set_duty_cycle(dc)
                sleep(2.0)
                rpm = float(rpm_calc.estimate(2))
                measured_rpms.append(rpm)
                logger.debug(f"Detected {rpm=:.1f} RPM @ {dc=}%")

                # log progress
                lc.mqtt_client.publish(
                    f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                    count / n_samples * 100,
                )
                logger.debug(f"Progress: {count / n_samples:.0%}")

        # drop any 0 in RPM, too little DC
        filtered = [(dc, rpm) for dc, rpm in zip(dcs, measured_rpms) if rpm > 0]
        filtered_dcs, filtered_measured_rpms = zip(*filtered)
        return list(filtered_dcs), list(filtered_measured_rpms)


def _build_stirring_calibration_from_measurements(
    dcs: list[float],
    rpms: list[float],
    voltage: float,
    unit: str,
) -> SimpleStirringCalibration:
    (alpha, _), (beta, _) = simple_linear_regression(dcs, rpms)
    logger = create_logger("stirring_calibration", experiment="$experiment")
    logger.debug(f"rpm = {alpha:.2f} * dc% + {beta:.2f}")

    from pioreactor.utils.splines import spline_fit

    return SimpleStirringCalibration(
        pwm_hz=config.getfloat("stirring.config", "pwm_hz"),
        voltage=voltage,
        calibration_name=f"stirring-calibration-{current_utc_datetime().strftime('%Y-%m-%d_%H-%M')}",
        calibrated_on_pioreactor_unit=unit,
        created_at=current_utc_datetime(),
        curve_data_=spline_fit(dcs, rpms, knots="auto"),
        recorded_data={"x": dcs, "y": rpms},
    )


def run_stirring_calibration(
    min_dc: float | None = None, max_dc: float | None = None
) -> SimpleStirringCalibration:
    dcs, rpms = collect_stirring_measurements(min_dc=min_dc, max_dc=max_dc)
    return _build_stirring_calibration_from_measurements(
        dcs=dcs,
        rpms=rpms,
        voltage=voltage_in_aux(),
        unit=get_unit_name(),
    )


def _run_stirring_calibration_for_session(
    ctx: SessionContext,
    min_dc: float | None = None,
    max_dc: float | None = None,
) -> SimpleStirringCalibration:
    if ctx.executor and ctx.mode == "ui":
        payload = ctx.executor(
            "stirring_calibration",
            {"min_dc": min_dc, "max_dc": max_dc},
        )
        raw_dcs = payload["dcs"]
        raw_rpms = payload["rpms"]
        assert isinstance(raw_dcs, list)
        assert isinstance(raw_rpms, list)
        dcs = [float(dc) for dc in raw_dcs]
        rpms = [float(rpm) for rpm in raw_rpms]
        return _build_stirring_calibration_from_measurements(
            dcs=dcs,
            rpms=rpms,
            voltage=ctx.read_voltage(),
            unit=get_unit_name(),
        )
    return run_stirring_calibration(min_dc=min_dc, max_dc=max_dc)


def start_dc_based_session(
    target_device: Literal["stirring"],
    min_dc: float | None = None,
    max_dc: float | None = None,
) -> CalibrationSession:
    session_id = str(uuid.uuid4())
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id=session_id,
        protocol_name=DCBasedStirringProtocol.protocol_name,
        target_device=target_device,
        status="in_progress",
        step_id="intro",
        data={"min_dc": min_dc, "max_dc": max_dc},
        created_at=now,
        updated_at=now,
    )


class Intro(SessionStep):
    step_id = "intro"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.info(
            "Stirring DC-based calibration",
            "Insert a vial with a stir bar and the liquid volume you plan to use (water is fine). "
            "Stirring must be off before starting.",
        )
        step.metadata = {
            "image": {
                "src": "/static/svgs/prepare-vial-arrow-pioreactor.svg",
                "alt": "Insert a vial with a stir bar and the liquid volume you plan to use.",
                "caption": "Insert a vial with a stir bar and the liquid volume you plan to use.",
            }
        }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.has_inputs:
            return RunCalibration()
        return None


class RunCalibration(SessionStep):
    step_id = "run_calibration"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.action(
            "Record calibration",
            "Continue to run the stirring calibration. This will take a few minutes.",
        )

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        calibration = _run_stirring_calibration_for_session(
            ctx,
            min_dc=ctx.data["min_dc"],
            max_dc=ctx.data["max_dc"],
        )
        link = ctx.store_calibration(calibration, "stirring")
        ctx.complete({"calibrations": [link]})
        return CalibrationComplete()


_DC_BASED_STEPS: StepRegistry = {
    Intro.step_id: Intro,
    RunCalibration.step_id: RunCalibration,
}


class DCBasedStirringProtocol(CalibrationProtocol[Literal["stirring"]]):
    target_device = "stirring"
    protocol_name = "dc_based"
    title = "DC-based stirring calibration"
    description = "Maps duty cycle to RPM for the current stirrer configuration."
    requirements = (
        "Vial",
        "Stir bar",
        "Liquid (water is fine)",
    )
    step_registry: ClassVar[StepRegistry] = _DC_BASED_STEPS

    @classmethod
    def start_session(
        cls,
        target_device: Literal["stirring"],
        min_dc: float | None = None,
        max_dc: float | None = None,
    ) -> CalibrationSession:
        return start_dc_based_session(target_device, min_dc=min_dc, max_dc=max_dc)

    def run(
        self, target_device: Literal["stirring"], min_dc: str | None = None, max_dc: str | None = None
    ) -> SimpleStirringCalibration:
        session = start_dc_based_session(
            target_device,
            min_dc=float(min_dc) if min_dc is not None else None,
            max_dc=float(max_dc) if max_dc is not None else None,
        )
        calibrations = run_session_in_cli(_DC_BASED_STEPS, session)
        return calibrations[0]
