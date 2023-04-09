# -*- coding: utf-8 -*-
"""
maps DC -> RPM, and PID will correct any disturbances
This should be run with a vial in, with a stirbar. Water is fine.

"""
from __future__ import annotations

import json
from time import sleep

import click

from pioreactor.background_jobs import stirring
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.pubsub import publish
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.math_helpers import simple_linear_regression
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_latest_testing_experiment_name
from pioreactor.whoami import get_unit_name


def stirring_calibration(min_dc: int, max_dc: int) -> None:
    unit = get_unit_name()
    experiment = get_latest_testing_experiment_name()
    action_name = "stirring_calibration"
    logger = create_logger(action_name)

    with publish_ready_to_disconnected_state(unit, get_latest_experiment_name(), action_name):
        logger.info("Starting stirring calibration.")

        if is_pio_job_running("stirring"):
            logger.error(
                "Make sure Stirring job is off before running stirring calibration. Exiting."
            )
            return

        measured_rpms = []

        # go up and down to observe any hysteresis.
        dcs = (
            list(range(max_dc, min_dc, -3))
            + list(range(min_dc, max_dc, 3))
            + list(range(max_dc, min_dc - 3, -3))
        )
        n_samples = len(dcs)

        with stirring.RpmFromFrequency() as rpm_calc, stirring.Stirrer(
            target_rpm=0,
            unit=unit,
            experiment=experiment,
            rpm_calculator=None,
        ) as st:
            rpm_calc.setup()
            st.duty_cycle = (
                max_dc + min_dc
            ) / 2  # we start with a somewhat low value, s.t. the stir bar is caught.
            st.start_stirring()
            sleep(8)

            for count, dc in enumerate(dcs, start=1):
                st.set_duty_cycle(dc)
                sleep(8)
                rpm = rpm_calc(4)
                measured_rpms.append(rpm)
                logger.debug(f"Detected {rpm=:.1f} RPM @ {dc=}%")

                # log progress
                publish(
                    f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                    count / n_samples * 100,
                )
                logger.debug(f"Progress: {count/n_samples:.0%}")

        # drop any 0 in RPM, too little DC
        try:
            filtered_dcs, filtered_measured_rpms = zip(
                *filter(lambda d: d[1] > 0, zip(dcs, measured_rpms))
            )
        except ValueError:
            # the above can fail if all measured rpms are 0
            logger.error("No RPMs were measured. Is the stirring spinning?")
            return

        # since in practice, we want a look up from RPM -> required DC, we
        # set x=measure_rpms, y=dcs
        (rpm_coef, rpm_coef_std), (intercept, intercept_std) = simple_linear_regression(
            filtered_measured_rpms, filtered_dcs
        )
        logger.debug(f"{rpm_coef=}, {rpm_coef_std=}, {intercept=}, {intercept_std=}")

        if rpm_coef <= 0:
            logger.warning(
                "Something went wrong - detected negative correlation between RPM and stirring."
            )
            return

        if intercept <= 0:
            logger.warning("Something went wrong - the intercept should be greater than 0.")
            return

        with local_persistant_storage(action_name) as cache:
            cache["linear_v1"] = json.dumps(
                {
                    "rpm_coef": rpm_coef,
                    "intercept": intercept,
                    "timestamp": current_utc_timestamp(),
                }
            )
            cache["stirring_calibration_data"] = json.dumps(
                {
                    "timestamp": current_utc_timestamp(),
                    "data": {"dcs": dcs, "measured_rpms": measured_rpms},
                }
            )


@click.option(
    "--min-dc",
    help="value between 0 and 100",
    type=click.IntRange(0, 100),
)
@click.option(
    "--max-dc",
    help="value between 0 and 100",
    type=click.IntRange(0, 100),
)
@click.command(name="stirring_calibration")
def click_stirring_calibration(min_dc: int, max_dc: int) -> None:
    """
    Generate a lookup between stirring and voltage
    """

    if max_dc is None and min_dc is None:
        # seed with initial_duty_cycle
        config_initial_duty_cycle = config.getfloat("stirring", "initial_duty_cycle")
        min_dc, max_dc = round(config_initial_duty_cycle * 0.75), round(
            config_initial_duty_cycle * 1.33
        )
    elif (max_dc is not None) and (min_dc is not None):
        assert min_dc < max_dc, "min_dc >= max_dc"
    else:
        raise ValueError("min_dc and max_dc must both be set.")

    stirring_calibration(min_dc, max_dc)
