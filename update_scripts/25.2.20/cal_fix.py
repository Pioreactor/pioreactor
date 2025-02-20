# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations import load_calibration


for cal_file in list_of_calibrations_by_device("od"):
    cal = load_calibration("od", cal_file)
    if cal.x != "voltages" and cal.y != "od600s":
        continue

    # problem cal
    print(f"Fixing {cal.calibration_name}")
    cal.x = "OD600"
    cal.y = "Voltage"
    cal.recorded_data["x"], cal.recorded_data["y"] = cal.recorded_data["y"], cal.recorded_data["x"]
    cal.curve_data_ = []

    cal.save_to_disk_for_device("od")

print("Done!")
