# -*- coding: utf-8 -*-
# test_od_calibration
from __future__ import annotations

import pytest
from click.testing import CliRunner
from pioreactor import structs
from pioreactor.calibrations import load_active_calibration
from pioreactor.calibrations import load_calibration
from pioreactor.cli.calibrations import analyze_calibration
from pioreactor.cli.calibrations import run_calibration
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_unit_name


def test_analyze() -> None:
    cal = structs.OD600Calibration(
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=[2.0, 0.0],
        calibration_name="test_analyze",
        ir_led_intensity=90.0,
        angle="90",
        recorded_data={"x": [0, 0.5, 1.0, 1.5, 2.0], "y": [0, 1, 2, 3, 4]},
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )
    cal.save_to_disk_for_device("od90")

    runner = CliRunner()
    result = runner.invoke(
        analyze_calibration, ["--device", "od90", "--name", "test_analyze"], input="d\n2\ny"
    )
    assert not result.exception

    loaded_cal = load_calibration("od90", "test_analyze")
    assert len(loaded_cal.curve_data_) == 3


@pytest.mark.slow
def test_run_od_standards() -> None:
    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "70"):
        runner = CliRunner()
        result = runner.invoke(
            run_calibration,
            ["--device", "od90"],
            input="standards\nod-cal-2025-02-23\nY\nY\n1\nY\nY\n0.5\nY\nY\n0.1\nn\n0.0\nY\nd\n1\ny\ny\n",
        )
        assert not result.exception
        cal = load_calibration("od90", "od-cal-2025-02-23")
        assert len(cal.curve_data_) == 2  # two since it's linear
        assert cal.x == "OD600"
        assert cal.y == "Voltage"
        assert len(cal.recorded_data["x"]) == 4

    active_cal = load_active_calibration("od90")
    assert active_cal is not None
    assert active_cal.calibration_name == "od-cal-2025-02-23"
