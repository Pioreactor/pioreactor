# -*- coding: utf-8 -*-
"""
maps DC -> RPM, and PID will correct any disturbances
This should be run with a vial in, with a stirbar. Water is fine.

"""
from __future__ import annotations

from time import sleep

from pioreactor.background_jobs import stirring
from pioreactor.calibrations.utils import linspace
from pioreactor.config import config
from pioreactor.config import temporary_config_change
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


def run_stirring_calibration(
    min_dc: float | None = None, max_dc: float | None = None
) -> SimpleStirringCalibration:
    if max_dc is None and min_dc is None:
        # seed with initial_duty_cycle
        config_initial_duty_cycle = config.getfloat("stirring.config", "initial_duty_cycle", fallback=30)
        min_dc, max_dc = config_initial_duty_cycle * 0.66, clamp(0, config_initial_duty_cycle * 1.33, 100)
    elif (max_dc is not None) and (min_dc is not None):
        assert min_dc < max_dc, "min_dc >= max_dc"
    else:
        raise ValueError("min_dc and max_dc must both be set.")

    unit = get_unit_name()
    experiment = get_testing_experiment_name()
    action_name = "stirring_calibration"
    logger = create_logger(action_name, experiment="$experiment")

    with managed_lifecycle(unit, experiment, action_name) as lc:
        logger.info("Starting stirring calibration.")

        if is_pio_job_running("stirring"):
            logger.error("Make sure Stirring job is off before running stirring calibration. Exiting.")
            raise JobPresentError("Make sure Stirring job is off before running stirring calibration.")

        measured_rpms = []

        # go up and down to observe any hysteresis.
        dcs = linspace(max_dc, min_dc, 5) + linspace(min_dc, max_dc, 5) + linspace(max_dc, min_dc, 5)
        n_samples = len(dcs)

        with temporary_config_change(config, "stirring.config", "enable_dodging_od", "False"):
            with stirring.RpmFromFrequency() as rpm_calc, stirring.Stirrer(
                target_rpm=0, unit=unit, experiment=experiment, rpm_calculator=None, calibration=False
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
                    rpm = rpm_calc.estimate(2)
                    measured_rpms.append(rpm)
                    logger.debug(f"Detected {rpm=:.1f} RPM @ {dc=}%")

                    # log progress
                    lc.mqtt_client.publish(
                        f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                        count / n_samples * 100,
                    )
                    logger.debug(f"Progress: {count/n_samples:.0%}")

        # drop any 0 in RPM, too little DC
        try:
            filtered_dcs, filtered_measured_rpms = zip(*filter(lambda d: d[1] > 0, zip(dcs, measured_rpms)))
        except ValueError:
            # the above can fail if all measured rpms are 0
            logger.warning("No RPMs were measured. Is the stirring spinning?")
            raise ValueError("No RPMs were measured. Is the stirring spinning?")

        if len(filtered_dcs) <= n_samples * 0.75:
            # the above can fail if all measured rpms are 0
            logger.warning(
                "Not enough RPMs were measured. Is the stirring spinning and working correctly? Try changing your initial_duty_cycle."
            )
            raise ValueError("Not enough RPMs were measured.")

        (alpha, _), (beta, _) = simple_linear_regression(filtered_dcs, filtered_measured_rpms)
        logger.debug(f"rpm = {alpha:.2f} * dc% + {beta:.2f}")

        if alpha <= 0:
            logger.warning("Something went wrong - detected negative correlation between RPM and stirring.")
            raise ValueError("Negative correlation between RPM and stirring.")

        return SimpleStirringCalibration(
            pwm_hz=config.getfloat("stirring.config", "pwm_hz"),
            voltage=voltage_in_aux(),
            calibration_name=f"stirring-calibration-{current_utc_datetime().strftime('%Y-%m-%d_%H-%M-%S')}",
            calibrated_on_pioreactor_unit=unit,
            created_at=current_utc_datetime(),
            curve_data_=[alpha, beta],
            curve_type="poly",
            recorded_data={"x": list(filtered_dcs), "y": list(filtered_measured_rpms)},
        )
