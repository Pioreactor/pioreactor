# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3

import click
from pioreactor.structs import ODCalibration
from pioreactor.structs import SimplePeristalticPumpCalibration
from pioreactor.utils.timing import to_datetime
from pioreactor.whoami import get_unit_name


def convert_old_to_new_pump(old_cal: dict) -> tuple[SimplePeristalticPumpCalibration, str]:
    device = old_cal["type"]

    new_cal = SimplePeristalticPumpCalibration(
        calibration_name=old_cal["name"],
        calibrated_on_pioreactor_unit=get_unit_name(),
        created_at=to_datetime(old_cal["created_at"]),
        curve_data_=[old_cal["duration_"], old_cal["bias_"]],
        curve_type="poly",
        recorded_data={"x": old_cal["durations"], "y": old_cal["volumes"]},
        hz=old_cal["hz"],
        dc=old_cal["dc"],
        voltage=old_cal["voltage"],
    )
    return new_cal, device


def convert_old_to_new_od(old_cal: dict) -> tuple[ODCalibration, str]:
    device = "od"
    new_cal = ODCalibration(
        calibration_name=old_cal["name"],
        calibrated_on_pioreactor_unit=get_unit_name(),
        created_at=to_datetime(old_cal["created_at"]),
        curve_data_=old_cal["curve_data_"],
        curve_type="poly",
        recorded_data={"y": old_cal["voltages"], "x": old_cal["od600s"]},
        angle=old_cal["type"].split("_")[1],
        pd_channel=old_cal["pd_channel"],
        ir_led_intensity=old_cal["ir_led_intensity"],
    )
    return new_cal, device


def old_calibrations(sql_database: str):
    try:
        conn = sqlite3.connect(sql_database)
    except sqlite3.OperationalError:
        return
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM cache")

    for row in cursor.fetchall():
        data = json.loads(row[0])
        yield data


@click.command()
@click.argument("db_location")
def main(db_location: str) -> None:
    for old_cal in old_calibrations(db_location):
        try:
            print(f"Converting {old_cal['name']} to new calibration format.")
            if "pump" in old_cal["type"]:
                new_cal, device = convert_old_to_new_pump(old_cal)
            elif "od" in old_cal["type"]:
                new_cal, device = convert_old_to_new_od(old_cal)
        except Exception as e:
            print(f"Failed to convert {old_cal['name']}: {e}")
            continue

        new_cal.save_to_disk_for_device(device)


if __name__ == "__main__":
    main()
