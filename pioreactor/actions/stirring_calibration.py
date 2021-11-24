# -*- coding: utf-8 -*-
"""
maps DC -> RPM, and PID will correct any disturbances
This should be run with a vial in, with a stirbar. Water is fine.

"""
import time, click, json
from pioreactor.pubsub import publish_to_pioreactor_cloud, publish

from pioreactor.background_jobs import stirring
from pioreactor.utils.math_helpers import simple_linear_regression
from pioreactor.whoami import (
    get_unit_name,
    get_latest_testing_experiment_name,
)
from pioreactor.logging import create_logger
from pioreactor.config import config
from pioreactor.utils import (
    is_pio_job_running,
    publish_ready_to_disconnected_state,
    local_persistant_storage,
)
from pioreactor.utils.timing import current_utc_time


def stirring_calibration():

    unit = get_unit_name()
    experiment = get_latest_testing_experiment_name()
    action_name = "stirring_calibration"
    logger = create_logger(action_name)

    with publish_ready_to_disconnected_state(unit, experiment, action_name):

        logger.info("Starting stirring calibration.")

        if is_pio_job_running("stirring"):
            logger.error(
                "Make sure Stirring job is off before running stirring calibration. Exiting."
            )
            return

        # seed with initial_duty_cycle
        config_initial_duty_cycle = round(
            config.getfloat("stirring", "initial_duty_cycle")
        )

        # we go up and down to exercise any hysteresis in the system
        if config_initial_duty_cycle < 50:
            dcs = (
                list(range(25, 50, 5)) + list(range(50, 25, -5)) + list(range(22, 47, 5))
            )
        else:
            dcs = (
                list(range(85, 40, -5)) + list(range(39, 85, 5)) + list(range(88, 58, -5))
            )

        measured_rpms = []

        with stirring.RpmFromFrequency() as rpm_calc, stirring.Stirrer(
            target_rpm=0,
            unit=unit,
            experiment=experiment,
            rpm_calculator=None,
        ) as st:

            st.duty_cycle = dcs[0]
            st.start_stirring()
            time.sleep(8)
            n_samples = len(dcs)

            for count, dc in enumerate(dcs, start=1):
                st.set_duty_cycle(dc)
                time.sleep(8)
                rpm = rpm_calc(4)
                measured_rpms.append(rpm)

                # log progress
                publish(
                    f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                    count // n_samples * 100,
                )
                logger.debug(f"Progress: {count/n_samples:.0%}")

        publish_to_pioreactor_cloud(action_name, json=dict(zip(dcs, measured_rpms)))
        logger.debug(list(zip(dcs, measured_rpms)))

        # drop any 0 in RPM, too little DC
        try:
            dcs, measured_rpms = zip(*filter(lambda d: d[1] > 0, zip(dcs, measured_rpms)))
        except ValueError:
            # the above can fail if all measured rpms are 0
            logger.error("No RPMs were measured. Is the stirring spinning?")
            return

        # since in practice, we want a look up from RPM -> required DC, we
        # set x=measure_rpms, y=dcs
        (rpm_coef, rpm_coef_std), (intercept, intercept_std) = simple_linear_regression(
            measured_rpms, dcs
        )
        logger.debug(f"{rpm_coef=}, {rpm_coef_std=}, {intercept=}, {intercept_std=}")

        if rpm_coef <= 0:
            logger.warning(
                "Something went wrong - detected negative correlation between RPM and stirring."
            )
            return

        if intercept <= 0:
            logger.warning(
                "Something went wrong - the intercept should be greater than 0."
            )
            return

        with local_persistant_storage(action_name) as cache:
            cache["linear_v1"] = json.dumps(
                {
                    "rpm_coef": rpm_coef,
                    "intercept": intercept,
                    "timestamp": current_utc_time(),
                }
            )


@click.command(name="stirring_calibration")
def click_stirring_calibration():
    """
    (Optional) Generate a lookup between stirring and voltage
    """
    stirring_calibration()
