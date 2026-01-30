# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor import structs
from pioreactor.calibrations import CALIBRATION_PATH
from pioreactor.calibrations import list_of_calibrations_by_device
from pioreactor.calibrations import load_calibration
from pioreactor.utils import local_persistent_storage


SOURCE_DEVICE = "od"


def get_target_device_for_calibration(calibration: structs.ODCalibration) -> str:
    return f"od{calibration.angle}"


def move_calibration_file(calibration: structs.ODCalibration, target_device: str) -> tuple[bool, bool]:
    source_path = calibration.path_on_disk_for_device(SOURCE_DEVICE)
    target_path = calibration.path_on_disk_for_device(target_device)

    if target_path.exists():
        if source_path.exists() and target_path.read_bytes() == source_path.read_bytes():
            source_path.unlink()
            print(f"Removed duplicate legacy calibration file {source_path}")
            return False, True

        print(f"Skipping {calibration.calibration_name}: target already exists at {target_path}.")
        return False, False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_path.rename(target_path)
    except FileNotFoundError:
        return False, False

    print(f"Moved {calibration.calibration_name} ({calibration.angle}°) to {target_path}")
    return True, False


def find_target_device_for_active_calibration(calibration_name: str) -> str | None:
    matches = []
    for device in list_target_od_devices():
        path = CALIBRATION_PATH / device / f"{calibration_name}.yaml"
        if path.exists():
            matches.append(device)

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        print(
            f"Multiple calibrations named '{calibration_name}' found in {matches}; leaving active calibration unchanged."
        )
    return None


def list_target_od_devices() -> list[str]:
    devices = {"od45", "od90", "od135"}
    if CALIBRATION_PATH.exists():
        for entry in CALIBRATION_PATH.iterdir():
            if entry.is_dir() and entry.name.startswith("od") and entry.name != SOURCE_DEVICE:
                devices.add(entry.name)
    return sorted(devices)


def migrate_active_calibration(calibration_name: str, target_device: str) -> None:
    with local_persistent_storage("active_calibrations") as cache:
        if cache.get(target_device) != calibration_name:
            cache[target_device] = calibration_name
            print(f"Set active calibration for {target_device} to {calibration_name}.")

        if cache.get(SOURCE_DEVICE) == calibration_name:
            del cache[SOURCE_DEVICE]
            print("Removed legacy active calibration key 'od'.")


def migrate_od_calibrations() -> None:
    active_name = None
    with local_persistent_storage("active_calibrations") as cache:
        active_name = cache.get(SOURCE_DEVICE)

    updated_active = False
    for cal_file in list_of_calibrations_by_device(SOURCE_DEVICE):
        try:
            calibration = load_calibration(SOURCE_DEVICE, cal_file)
        except Exception as exc:
            print(f"Skipping {cal_file}: unable to load ({exc}).")
            continue

        if not isinstance(calibration, structs.ODCalibration):
            print(f"Skipping {cal_file}: not an OD calibration.")
            continue

        target_device = get_target_device_for_calibration(calibration)
        moved, removed_duplicate = move_calibration_file(calibration, target_device)

        if (
            active_name is not None
            and calibration.calibration_name == active_name
            and (moved or removed_duplicate)
        ):
            migrate_active_calibration(active_name, target_device)
            updated_active = True

    if active_name is not None and not updated_active:
        _target_device = find_target_device_for_active_calibration(active_name)
        if _target_device is not None:
            migrate_active_calibration(active_name, _target_device)

    print("Done!")


migrate_od_calibrations()
