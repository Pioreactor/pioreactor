# -*- coding: utf-8 -*-
# stirring calibration
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

from pioreactor.utils import (
    is_pio_job_running,
    publish_ready_to_disconnected_state,
    local_persistant_storage,
)


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

        dcs = list(range(95, 45, -5)) + list(
            range(46, 96, 5)
        )  # we go up and down to exercise any hystersis in the system
        measured_rpms = []

        rpm_calc = stirring.RpmFromFrequency()

        st = stirring.Stirrer(
            target_rpm=0,
            unit=unit,
            experiment=experiment,
            rpm_calculator=None,
        )
        st.duty_cycle = dcs[0]
        st.start_stirring()
        time.sleep(10)
        n_samples = len(dcs)

        for count, dc in enumerate(dcs):
            st.set_duty_cycle(dc)
            time.sleep(8)
            measured_rpms.append(rpm_calc(4))

            # log progress
            publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/percent_progress",
                count / n_samples * 100,
            )
            logger.debug(f"Progress: {count/n_samples:.0%}")

        rpm_calc.cleanup()
        st.set_state(st.DISCONNECTED)

        publish_to_pioreactor_cloud(
            "stirring_calibration", json=dict(zip(dcs, measured_rpms))
        )

        # drop any 0 in RPM, too little DC
        dcs, measured_rpms = zip(*filter(lambda d: d[1] > 0, zip(dcs, measured_rpms)))
        print(dcs, measured_rpms)

        # since in practice, we want a look up from RPM -> required DC, we
        # set x=measure_rpms, y=dcs
        (rpm_coef, _), (intercept, _) = simple_linear_regression(measured_rpms, dcs)
        print(rpm_coef, intercept)

        with local_persistant_storage("stirring_calibration") as cache:
            cache["linear_v1"] = json.dumps(
                {"rpm_coef": rpm_coef, "intercept": intercept}
            )


@click.command(name="stirring_calibration")
def click_stirring_calibration():
    """
    (Optional) Generate a lookup between stirring and voltage
    """
    stirring_calibration()
