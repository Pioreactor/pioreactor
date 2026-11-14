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


@pytest.mark.parametrize("fit", ["poly", "spline"])
def test_analyze_produces_reproducible_unanchored_calibration(fit: str) -> None:
    # The zero-OD observation is an ordinary measurement, not an implicit constraint.
    cal = structs.OD600Calibration(
        created_at=current_utc_datetime(),
        curve_data_=structs.PolyFitCoefficients(
            coefficients=[
                -0.009124890919507432,
                0.05407609911685577,
                0.018930870855710855,
                0.0008976697259911073,
            ]
        ),
        calibration_name=f"test_unanchored_{uuid4().hex}",
        ir_led_intensity=80.0,
        angle="90",
        recorded_data={
            "x": [0.035, 0.1575, 0.337, 0.599, 1.037, 1.58, 2.203, 4.112, 0.0],
            "y": [
                0.0014172847597772925,
                0.0063852726292845385,
                0.017265524020566546,
                0.03447678457829678,
                0.0633929056237781,
                0.1268558919741471,
                0.21046957853974058,
                0.358428297140704,
                0.00024270398714387712,
            ],
        },
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )
    cal.save_to_disk_for_device("od90")
    try:
        result = CliRunner().invoke(
            analyze_calibration,
            ["--device", "od90", "--name", cal.calibration_name, "--fit", fit],
            input="d\n3\ny\n" if fit == "poly" else "y\n",
        )
        assert result.exception is None, result.output
        refitted = load_calibration("od90", cal.calibration_name)
        assert isinstance(refitted, structs.OD600Calibration)
        from pioreactor.calibrations.refit import refit_calibration

        assert refitted.recorded_data == cal.recorded_data
        recreated = refit_calibration(refitted, [True] * len(refitted.recorded_data["x"]))
        for x in refitted.recorded_data["x"]:
            assert recreated.x_to_y(x) == pytest.approx(refitted.x_to_y(x), abs=1e-10)
    finally:
        cal.path_on_disk_for_device("od90").unlink()


@pytest.mark.slow
@pytest.mark.parametrize("rpm", [0, 500])
def test_run_od_standards(rpm: float) -> None:
    calibration_name = f"od-cal-{uuid4().hex}"
    input_ = "\n".join(
        [
            "",
            calibration_name,
            "4",
            str(rpm),
            "",
            "0.0",
            "",
            "1",
            "",
            "0.5",
            "",
            "0.1",
            "y",
        ]
    )
    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "70"):
        runner = CliRunner()
        result = runner.invoke(run_calibration, ["--device", "od90"], input=input_)
        assert not result.exception
        cal = load_calibration("od90", calibration_name)
        assert cal.curve_data_.type == "spline"
        assert cal.x == "OD600"
        assert cal.y == "Voltage"
        assert cal.recorded_data["x"] == [0.0, 1.0, 0.5, 0.1]

    active_cal = load_active_calibration("od90")
    assert active_cal is not None
    assert active_cal.calibration_name == calibration_name
