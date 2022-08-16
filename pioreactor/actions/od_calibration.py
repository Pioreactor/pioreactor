# -*- coding: utf-8 -*-
from __future__ import annotations

from time import sleep

import click
import plotext as plt
from msgspec.json import encode

from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring as stirring
from pioreactor.config import config
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_latest_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env

"""
0. CONFIRM: angle (what's in config.ini), unique name,
1. Add 10ml of HDC to vial with stir bar.
   - ASK What is the OD600 of that culture: float
   - ASK what is the minimum OD600 you want to calibrate for.
2. Put vial in Pioreactor. CONFIRM Y/N
3. Start stirring.
4. Record OD reading.
5. For 10 times:
    5.1 Ask to add 1ml of DI water (potential editable). Cap. CONFIRM Y/N
    5.2 Record OD reading.
    5.3 Confirm / ignore / redo reading? (maybe)
6. Remove vial, reduce volume to 10ml (half). go back to 5.
7. If inferred OD600 < minimum OD600, stop.
9. Run curve fitting,
8. Show plot with data and curve, CONFIRM Y/N
9. save data locally, print JSON results to user.
"""


def introduction():
    click.echo(
        """This routine will calibrate the current Pioreactor to (offline) OD600 readings. You'll need:
    1. A Pioreactor
    2. 10ml of a culture with density the most you'll ever observe, with it's OD600 measurement.
    3. Micro-pipette with available range 100-1000 uL volume
"""
    )


def get_metadata_from_user():
    name = click.prompt("Provide a unique name for this calibration", type=str)
    initial_od600 = click.prompt(
        "Provide the OD600 measurement of your initial culture", type=float
    )
    minimum_od600 = click.prompt(
        "Provide the minimum OD600 measurement you want to calibrate to", default=0.1, type=float
    )
    angle = click.confirm(
        f"Confirm using angle {config['od_config.photodiode_channel']['2']}°", abort=True
    )
    return name, initial_od600, minimum_od600, angle


def setup_HDC_instructions():
    click.clear()
    click.echo(
        """ Setting up:
    1. Add 10ml of your culture to the glass vial, with a stir bar. Add cap.
    2. Place into Pioreactor.
"""
    )


def start_stirring():
    while not click.confirm("Reading to start stirring?"):
        pass
    st = stirring(unit=get_unit_name(), experiment=get_latest_testing_experiment_name())
    click.echo("Starting stirring.")
    st.block_until_rpm_is_close_to_target()
    return st


def start_recording_and_diluting(initial_od600, minimum_od600):

    inferred_od600 = initial_od600
    voltages = []
    inferred_od600s = []
    current_volume_in_vial = initial_volume_in_vial = 10.0
    click.echo("Starting OD recordings.")

    with start_od_reading(
        config.get("od_config.photodiode_channel", "1"),
        config.get("od_config.photodiode_channel", "2"),
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_latest_testing_experiment_name()
        # calibration=False,,..
    ) as od_reader:

        for _ in range(4):
            od_reader.record_from_adc()

        while True:
            od_readings1 = od_reader.record_from_adc()
            od_readings2 = od_reader.record_from_adc()

            voltages.append(
                0.5 * (od_readings1.od_raw["2"].voltage + od_readings2.od_raw["2"].voltage)
            )
            inferred_od600s.append(inferred_od600)

            for i in range(10):  # 10 assumes 1ml dilutions
                click.clear()
                # plot
                plt.scatter(inferred_od600s, voltages)
                plt.title("Calibration (ongoing)")
                plt.clc()
                plt.plot_size(100, 20)
                plt.xlim(minimum_od600, initial_od600)
                plt.show()
                click.echo()
                click.echo("Add 1ml of DI water to vial.")

                while not click.confirm("Continue?"):
                    pass

                current_volume_in_vial = current_volume_in_vial + 1.0  # assumes 1ml

                sleep(1.0)

                od_readings1 = od_reader.record_from_adc()
                od_readings2 = od_reader.record_from_adc()
                voltages.append(
                    0.5 * (od_readings1.od_raw["2"].voltage + od_readings2.od_raw["2"].voltage)
                )

                inferred_od600 = (
                    inferred_od600 * (current_volume_in_vial - 1) / current_volume_in_vial
                )
                inferred_od600s.append(inferred_od600)

                if inferred_od600 <= minimum_od600:
                    break

            else:
                continue  # only executed if the inner loop did NOT break

            if inferred_od600 <= minimum_od600:
                break
            else:
                click.echo(
                    "Remove vial and reduce volume back to 10ml. Place back into Pioreactor."
                )
                click.confirm("Continue?", abort=True)
                current_volume_in_vial = initial_volume_in_vial
                sleep(1.0)

        return inferred_od600s, voltages


def calculate_curve_of_best_fit(voltages, inferred_od600s):
    return None


def show_results_and_confirm_with_user(curve, voltages, inferred_od600s):
    plt.clf()
    plt.scatter(inferred_od600s, voltages)
    plt.title("Calibration (ongoing)")
    plt.clc()
    plt.plot_size(100, 20)
    plt.show()
    click.confirm("Confirm?", abort=True)


def save_results_locally(
    curve, voltages, inferred_od600s, angle, name, initial_od600, minimum_od600
):
    timestamp = current_utc_timestamp()

    with local_persistant_storage("calibration") as cache:
        cache[name] = encode(
            {
                "angle": angle,
                "timestamp": timestamp,
                "name": name,
                "initial_od600": initial_od600,
                "minimum_od600": minimum_od600,
                "curve": curve,
                "voltages": voltages,
                "inferred_od600s": inferred_od600s,
            }
        )


def od_calibration():
    introduction()
    name, initial_od600, minimum_od600, angle = get_metadata_from_user()
    setup_HDC_instructions()

    with start_stirring():

        inferred_od600s, voltages = start_recording_and_diluting(initial_od600, minimum_od600)

    curve = calculate_curve_of_best_fit(voltages, inferred_od600s)

    show_results_and_confirm_with_user(curve, voltages, inferred_od600s)
    save_results_locally(
        curve, voltages, inferred_od600s, angle, name, initial_od600, minimum_od600
    )

    click.echo("Finished ✅")
    return


@click.command(name="od_calibration")
def click_od_calibration():
    """
    Calibrate OD600 to voltages
    """
    od_calibration()
