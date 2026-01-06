# -*- coding: utf-8 -*-
from __future__ import annotations

from time import sleep
from typing import cast

import click
from click import echo
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.od_reading import average_over_od_readings
from pioreactor.background_jobs.od_reading import REF_keyword
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.calibrations import utils as calibration_utils
from pioreactor.calibrations.cli_helpers import info
from pioreactor.calibrations.cli_helpers import info_heading
from pioreactor.calibrations.cli_helpers import red
from pioreactor.config import config
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import managed_lifecycle
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


STANDARD_OD = 1.0
DEFAULT_TARGET_ANGLES = {"45", "90", "135"}
OD_REFERENCE_STANDARD_SAMPLES = 5


def introduction() -> None:
    click.clear()
    info_heading("OD reference standard calibration")
    info("This routine creates OD calibrations using the optical reference standard.")


def get_ir_led_intensity() -> float:
    ir_intensity_setting = config.get("od_reading.config", "ir_led_intensity")
    if ir_intensity_setting == "auto":
        echo(
            red(
                "ir_led_intensity must be numeric when creating OD calibrations from the optical reference standard. Try 80."
            )
        )
        raise click.Abort()
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
        echo(red("No configured PD channels match the selected device."))
        raise click.Abort()

    return channel_angle_map


def record_reference_standard(ir_led_intensity: float) -> structs.ODReadings:
    info("Recording OD readings...")
    with start_od_reading(
        config["od_config.photodiode_channel"],
        interval=None,
        unit=get_unit_name(),
        fake_data=is_testing_env(),
        experiment=get_testing_experiment_name(),
        calibration=False,
        ir_led_intensity=ir_led_intensity,
    ) as od_reader:
        for _ in range(3):
            sleep(5)
            od_reader.record_from_adc()

        od_readings_samples: list[structs.ODReadings] = []
        for _ in range(OD_REFERENCE_STANDARD_SAMPLES):
            od_readings = od_reader.record_from_adc()
            if od_readings is None:
                echo(red("Unable to record OD readings."))
                raise click.Abort()
            od_readings_samples.append(od_readings)

    averaged_od_readings = average_over_od_readings(*od_readings_samples)
    averaged_od_summary = ", ".join(
        f"channel {pd_channel} ({od_reading.angle} deg)={od_reading.od:.6f}"
        for pd_channel, od_reading in sorted(averaged_od_readings.ods.items())
    )
    info(f"Averaged OD readings: {averaged_od_summary}")
    return averaged_od_readings


def run_od_calibration(target_device: pt.ODCalibrationDevices) -> list[structs.ODCalibration]:
    unit = get_unit_name()
    experiment = get_testing_experiment_name()
    calibrations: list[structs.ODCalibration] = []

    with managed_lifecycle(unit, experiment, "od_calibration"):
        introduction()

        if is_pio_job_running("od_reading"):
            echo(red("OD reading should be turned off."))
            raise click.Abort()

        ir_led_intensity = get_ir_led_intensity()
        channel_angle_map = get_channel_angle_map(target_device)

        od_readings = record_reference_standard(ir_led_intensity)
        recorded_ods = [0.0, 1000 * STANDARD_OD]
        timestamp = current_utc_datetime().strftime("%Y-%m-%d")

        for pd_channel, od_reading in od_readings.ods.items():
            if pd_channel not in channel_angle_map:
                continue
            angle = channel_angle_map[pd_channel]

            recorded_voltages = [0.0, 1000 * od_reading.od]
            curve_data_ = calibration_utils.calculate_poly_curve_of_best_fit(
                recorded_ods, recorded_voltages, degree=1
            )
            if len(curve_data_) == 2:
                slope, intercept = curve_data_
                info(
                    f"Fitted linear curve for od{angle} (channel {pd_channel}): "
                    f"y = {slope:.6f}x + {intercept:.6f}"
                )
            else:
                info(
                    f"Fitted linear curve for od{angle} (channel {pd_channel}): "
                    f"coefficients={curve_data_}"
                )

            calibration = structs.ODCalibration(
                created_at=current_utc_datetime(),
                calibrated_on_pioreactor_unit=unit,
                calibration_name=f"od{angle}-optical-reference-standard-{timestamp}",
                angle=angle,
                curve_data_=curve_data_,
                curve_type="poly",
                recorded_data={"x": recorded_ods, "y": recorded_voltages},
                ir_led_intensity=ir_led_intensity,
                pd_channel=pd_channel,
            )
            calibrations.append(calibration)

        if not calibrations:
            echo(red("No matching channels were recorded for this calibration."))
            raise click.Abort()

        info("Finished reference standard calibration.")
        return calibrations
