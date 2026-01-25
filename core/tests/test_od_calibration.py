# -*- coding: utf-8 -*-
# test_od_calibration
from uuid import uuid4

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
        curve_data_=structs.PolyFitCoefficients(coefficients=[2.0, 0.0]),
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
    assert len(loaded_cal.curve_data_.coefficients) == 3


@pytest.mark.slow
def test_run_od_standards() -> None:
    calibration_name = f"od-cal-{uuid4().hex}"
    input_ = "\n".join(
        [
            "",
            calibration_name,
            "500",
            "",
            "1",
            "",
            "",
            "0.5",
            "",
            "",
            "0.1",
            "continue to blank (media only)",
            "",
            "0.0",
            "y",
        ]
    )
    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "70"):
        runner = CliRunner()
        result = runner.invoke(run_calibration, ["--device", "od90"], input=input_)
        assert not result.exception
        cal = load_calibration("od90", calibration_name)
        if cal.curve_data_.type == "poly":
            expected_degree = min(3, max(1, len(cal.recorded_data["x"]) - 1))
            assert len(cal.curve_data_.coefficients) == expected_degree + 1
        else:
            assert cal.curve_data_.type == "spline"
        assert cal.x == "OD600"
        assert cal.y == "Voltage"
        assert len(cal.recorded_data["x"]) == 4

    active_cal = load_active_calibration("od90")
    assert active_cal is not None
    assert active_cal.calibration_name == calibration_name
