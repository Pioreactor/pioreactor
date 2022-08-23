# -*- coding: utf-8 -*-
from __future__ import annotations

from time import sleep

import click
from msgspec.json import decode
from msgspec.json import encode

from pioreactor import structs
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring as stirring
from pioreactor.config import config
from pioreactor.pubsub import publish
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_latest_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def introduction():
    click.clear()
    click.echo(
        """This routine will calibrate the current Pioreactor to (offline) OD600 readings. You'll need:
    1. A Pioreactor
    2. At least 10mL of a culture with density the most you'll ever observe, and its OD600 measurement
    3. Micro-pipette
    4. Accurate 10mL measurement tool
"""
    )


def get_metadata_from_user():
    with local_persistant_storage("od_calibrations") as cache:
        while True:
            name = click.prompt("Provide a name for this calibration", type=str)
            if name not in cache:
                break
            else:
                if click.confirm("❗️ Name already exists. Do you wish to overwrite?"):
                    break

    initial_od600 = click.prompt(
        "Provide the OD600 measurement of your initial culture", type=click.FloatRange(min=0.01, clamp=False)
    )

    minimum_od600 = click.prompt(
        "Provide the minimum OD600 measurement you want to calibrate to", type=click.FloatRange(min=0.01, max=initial_od600, clamp=True)
    )

    dilution_amount = click.prompt(
        "Provide the volume to be added to your vial (default = 1 mL)", default=1, type=click.FloatRange(min=0.01, max=10, clamp=False)
    )

    from math import log2

    number_of_points = int(log2(initial_od600 / minimum_od600) * (10 / dilution_amount))

    click.echo(f"This will require about {number_of_points} measurements.")

    ref_channel = config["od_config.photodiode_channel_reverse"]["REF"]
    signal_channel = "1" if ref_channel == "2" else "2"

    click.confirm(
        f"Confirm using channel {signal_channel} with angle {config['od_config.photodiode_channel'][signal_channel]}° position in the Pioreactor",
        abort=True,
        default=True,
    )
    angle = str(config["od_config.photodiode_channel"][signal_channel])
    return name, initial_od600, minimum_od600, dilution_amount, angle, signal_channel


def setup_HDC_instructions():
    click.clear()
    click.echo(
        """ Setting up:
    1. Add 10ml of your culture to the glass vial, with a stir bar. Add cap.
    2. Place into Pioreactor.
"""
    )


def start_stirring():
    while not click.confirm("Reading to start stirring?", default=True):
        pass

    click.echo("Starting stirring.")

    st = stirring(
        target_rpm=config.getfloat("stirring", "target_rpm"),
        unit=get_unit_name(),
        experiment=get_latest_testing_experiment_name(),
    )
    st.block_until_rpm_is_close_to_target(abs_tolerance=120)
    return st


def plot_data(
    x, y, title, x_min=None, x_max=None, interpolation_curve=None, highlight_recent_point=True
):
    import plotext as plt  # type: ignore

    plt.clf()

    plt.scatter(x, y, marker="hd")

    if highlight_recent_point:
        plt.scatter([x[-1]], [y[-1]], color=204, marker="hd")

    plt.theme("pro")
    plt.title(title)
    plt.plot_size(105, 22)

    if interpolation_curve:
        plt.plot(x, [interpolation_curve(x_) for x_ in x], color=204)
        plt.plot_size(145, 42)

    plt.xlim(x_min, x_max)
    plt.show()


def start_recording_and_diluting(initial_od600, minimum_od600, dilution_amount, signal_channel):

    inferred_od600 = initial_od600
    voltages = []
    inferred_od600s = []
    current_volume_in_vial = initial_volume_in_vial = 10
    number_of_plotpoints = int((20 - initial_volume_in_vial) / dilution_amount)
    click.echo("Starting OD recordings.")

    with start_od_reading(
        config.get("od_config.photodiode_channel", "1"),
        config.get("od_config.photodiode_channel", "2"),
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_latest_testing_experiment_name(),
        use_calibration=False,
    ) as od_reader:

        def get_voltage_from_adc() -> float:
            od_readings1 = od_reader.record_from_adc()
            od_readings2 = od_reader.record_from_adc()
            return 0.5 * (od_readings1.ods[signal_channel].od + od_readings2.ods[signal_channel].od)

        for _ in range(4):
            od_reader.record_from_adc()

        while inferred_od600 > minimum_od600:

            if inferred_od600 < initial_od600 and click.confirm(
                "Do you want to enter a new OD600 value for the current density?"
            ):
                inferred_od600 = click.prompt("New measured OD600", type=float)

            inferred_od600s.append(inferred_od600)

            voltages.append(get_voltage_from_adc())

            for i in range(number_of_plotpoints):
                click.clear()
                plot_data(
                    inferred_od600s,
                    voltages,
                    title="OD Calibration (ongoing)",
                    x_min=minimum_od600,
                    x_max=initial_od600,
                )
                click.echo()
                click.echo(f"Add {dilution_amount}ml of DI water to vial.")

                while not click.confirm("Continue?", default=True):
                    pass

                current_volume_in_vial = current_volume_in_vial + dilution_amount

                for i in range(4):
                    click.echo(".", nl=False)
                    sleep(0.5)

                click.echo(".", nl=False)
                voltages.append(get_voltage_from_adc())
                click.echo(".", nl=False)

                inferred_od600 = (
                    inferred_od600
                    * (current_volume_in_vial - dilution_amount)
                    / current_volume_in_vial
                )
                inferred_od600s.append(inferred_od600)

                if inferred_od600 <= minimum_od600:
                    break

            else:
                # executed if the loop did not break
                click.clear()
                plot_data(
                    inferred_od600s,
                    voltages,
                    title="OD Calibration (ongoing)",
                    x_min=minimum_od600,
                    x_max=initial_od600,
                )
                click.echo()
                click.echo(click.style("Stop❗", fg="red"))
                click.echo("Carefully remove vial.")
                click.echo("(Optional: take new OD600 reading with external instrument.)")
                click.echo("Reduce volume in vial back to 10ml.")
                click.echo("Confirm vial outside is dry and clean. Place back into Pioreactor.")
                while not click.confirm("Continue?", default=True):
                    pass
                current_volume_in_vial = initial_volume_in_vial
                sleep(1.0)

        click.clear()
        plot_data(
            inferred_od600s,
            voltages,
            title="OD Calibration (ongoing)",
            x_min=minimum_od600,
            x_max=initial_od600,
        )
        click.echo("Empty the vial and replace with 10 mL of the media you used.")
        inferred_od600 = click.prompt("What is the OD600 of your blank?", default=0, type=float)
        click.echo("Confirm vial outside is dry and clean. Place back into Pioreactor.")
        while not click.confirm("Continue?", default=True):
            pass

        voltages.append(get_voltage_from_adc())
        inferred_od600s.append(inferred_od600)

        return inferred_od600s, voltages


def calculate_curve_of_best_fit(voltages, inferred_od600s, degree):
    import numpy as np

    # weigh the last point, the "blank measurement", more.
    # 1. It's far away from the other points
    # 2. We have prior knowledge that OD~0 when V~0.
    n = len(voltages)
    weights = np.ones_like(voltages)
    weights[-1] = n / 2

    try:
        coefs = np.polyfit(inferred_od600s, voltages, deg=degree, w=weights).tolist()
    except Exception:
        click.echo("Unable to fit.")
        coefs = np.zeros(degree)

    return coefs, "poly"


def show_results_and_confirm_with_user(curve, curve_type, voltages, inferred_od600s):
    click.clear()

    if curve_type == "poly":
        import numpy as np

        def curve_callable(x):
            return np.polyval(curve, x)

    else:
        curve_callable = None

    plot_data(
        inferred_od600s,
        voltages,
        title="OD Calibration with curve of best fit",
        interpolation_curve=curve_callable,
        highlight_recent_point=False,
    )
    r = click.prompt(
        """
What next?

Y: confirm and save to disk
n: abort completely
d: choose a new degree for polynomial fit

""",
        type=click.Choice(["Y", "n", "d"]),
    )
    if r == "Y":
        return True, None
    elif r == "n":
        click.exit()
    elif r == "d":
        d = click.prompt("Enter new degree", type=int)
        return False, d


def save_results_locally(
    curve_data_: list[float],
    curve_type: str,
    voltages: list[float],
    inferred_od600s: list[float],
    angle,
    name: str,
    maximum_od600: float,
    minimum_od600: float,
    signal_channel,
) -> structs.ODCalibration:
    data_blob = structs.ODCalibration(
        timestamp=current_utc_timestamp(),
        name=name,
        angle=angle,
        maximum_od600=maximum_od600,
        minimum_od600=0,
        minimum_voltage=min(voltages),
        maximum_voltage=max(voltages),
        curve_data_=curve_data_,
        curve_type=curve_type,
        voltages=voltages,
        inferred_od600s=inferred_od600s,
        ir_led_intensity=float(config["od_config"]["ir_led_intensity"]),
        pd_channel=signal_channel,
    )

    with local_persistant_storage("od_calibrations") as cache:
        cache[name] = encode(data_blob)

    with local_persistant_storage("current_od_calibration") as cache:
        cache[angle] = encode(data_blob)

    # send to MQTT
    publish(f"pioreactor/{get_unit_name()}/{UNIVERSAL_EXPERIMENT}/calibrations", encode(data_blob))

    return data_blob


def od_calibration():
    unit = get_unit_name()
    experiment = get_latest_testing_experiment_name()

    if is_pio_job_running("stirring", "od_reading"):
        raise ValueError("Stirring and OD reading should be turned off.")

    with publish_ready_to_disconnected_state(unit, experiment, "od_calibration"):

        introduction()
        (
            name,
            initial_od600,
            minimum_od600,
            dilution_amount,
            angle,
            signal_channel,
        ) = get_metadata_from_user()
        setup_HDC_instructions()

        with start_stirring():
            inferred_od600s, voltages = start_recording_and_diluting(
                initial_od600, minimum_od600, dilution_amount, signal_channel
            )

        degree = 4
        while True:
            curve, curve_type = calculate_curve_of_best_fit(voltages, inferred_od600s, degree)
            okay_with_result, degree = show_results_and_confirm_with_user(
                curve, curve_type, voltages, inferred_od600s
            )
            if okay_with_result:
                break

        data_blob = save_results_locally(
            curve,
            curve_type,
            voltages,
            inferred_od600s,
            angle,
            name,
            initial_od600,
            minimum_od600,
            signal_channel,
        )
        click.echo(click.style(f"Data for {name}", underline=True, bold=True))
        click.echo(data_blob)
        click.echo(f"Finished calibration of {name} ✅")
        return


@click.command(name="od_calibration")
@click.option("--display-current", is_flag=True)
def click_od_calibration(display_current):
    """
    Calibrate OD600 to voltages
    """
    if display_current:
        from pprint import pprint

        with local_persistant_storage("current_od_calibration") as c:
            for angle in c.keys():
                data_blob = decode(c[angle])
                voltages = data_blob["voltages"]
                ods = data_blob["inferred_od600s"]
                name, angle = data_blob["name"], data_blob["angle"]
                plot_data(
                    ods, voltages, title=f"{name}, {angle}°", highlight_recent_point=False
                )  # TODO: add interpolation curve
                click.echo(click.style(f"Data for {name}", underline=True, bold=True))
                pprint(data_blob)
                click.echo()
                click.echo()
                click.echo()

    else:
        od_calibration()
