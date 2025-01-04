# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from datetime import timezone

import pytest
from msgspec import ValidationError

from pioreactor.calibrations import CALIBRATION_PATH
from pioreactor.calibrations import load_active_calibration
from pioreactor.calibrations import load_calibration
from pioreactor.structs import ODCalibration
from pioreactor.utils import local_persistent_storage


@pytest.fixture
def temp_calibration_dir():
    calibrations_dir = CALIBRATION_PATH
    calibrations_dir.mkdir(parents=True, exist_ok=True)

    yield calibrations_dir


def test_save_and_load_calibration(temp_calibration_dir) -> None:
    # 1. Create an ODCalibration object (fully valid).
    od_cal = ODCalibration(
        calibration_name="my_test_cal",
        pioreactor_unit="unitA",
        created_at=datetime.now(timezone.utc),
        curve_data_=[1.0, 2.0, 3.0],
        curve_type="poly",
        x="voltage",
        y="od600",
        recorded_data={"x": [0.1, 0.2], "y": [0.3, 0.4]},
        ir_led_intensity=1.23,
        angle="90",
        pd_channel="2",
        maximum_od600=2.0,
        minimum_od600=0.0,
        minimum_voltage=0.1,
        maximum_voltage=5.0,
    )

    # 2. Save to disk
    od_cal.save_to_disk_for_device("od")
    # The calibration file should now exist in .pioreactor/storage/calibrations/od/

    # 3. Load from disk
    loaded_cal = load_calibration("od", "my_test_cal")
    assert isinstance(loaded_cal, ODCalibration)
    assert loaded_cal.calibration_name == "my_test_cal"
    assert loaded_cal.angle == "90"
    assert loaded_cal.curve_data_ == [1.0, 2.0, 3.0]

    # 4. Set as active
    od_cal.set_as_active_calibration_for_device("od")

    # 5. Load via load_active_calibration
    active_cal = load_active_calibration("od")
    assert isinstance(active_cal, ODCalibration)
    assert active_cal.calibration_name == "my_test_cal"


def test_load_calibration_missing_file(temp_calibration_dir) -> None:
    with pytest.raises(FileNotFoundError):
        load_calibration("od", "non_existent_cal")


def test_load_active_calibration_none(temp_calibration_dir) -> None:
    # Make sure 'od' key is not set in local_persistent_storage("active_calibrations")
    with local_persistent_storage("active_calibrations") as store:
        store.pop("od", None)

    cal = load_active_calibration("od")
    assert cal is None


def test_load_calibration_validation_error(temp_calibration_dir) -> None:
    # 1. Create the directory for "od" calibrations
    od_dir = temp_calibration_dir / "od"
    od_dir.mkdir(parents=True, exist_ok=True)

    # 2. Write some invalid YAML (missing required fields, or wrong structure)
    bad_calibration_file = od_dir / "bad_cal.yaml"
    bad_calibration_file.write_text(
        """
    calibration_name: "bad_cal"
    # missing many required fields
    # invalid structure
    something_unexpected: 123
    """
    )

    # 3. Attempt to load -> ValidationError
    with pytest.raises(ValidationError) as exc_info:
        load_calibration("od", "bad_cal")

    assert "Error reading bad_cal" in str(exc_info.value)
