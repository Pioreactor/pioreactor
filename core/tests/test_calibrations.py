# -*- coding: utf-8 -*-
from datetime import datetime
from datetime import timezone

import numpy as np
import pytest
from msgspec import ValidationError
from pioreactor import exc
from pioreactor.calibrations import CALIBRATION_PATH
from pioreactor.calibrations import CalibrationProtocol
from pioreactor.calibrations import get_calibration_protocols
from pioreactor.calibrations import load_active_calibration
from pioreactor.calibrations import load_calibration
from pioreactor.calibrations.utils import calculate_poly_curve_of_best_fit
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.structs import CalibrationBase
from pioreactor.structs import OD600Calibration
from pioreactor.structs import ODCalibration
from pioreactor.structs import PolyFitCoefficients
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_datetime


def _poly_curve(coefficients: list[float]) -> PolyFitCoefficients:
    return PolyFitCoefficients(coefficients=coefficients)


@pytest.fixture
def temp_calibration_dir():
    calibrations_dir = CALIBRATION_PATH
    calibrations_dir.mkdir(parents=True, exist_ok=True)

    yield calibrations_dir


def test_save_and_load_calibration(temp_calibration_dir) -> None:
    # 1. Create an OD600Calibration object (fully valid).
    od_cal = OD600Calibration(
        calibration_name="my_test_cal",
        calibrated_on_pioreactor_unit="unitA",
        created_at=datetime.now(timezone.utc),
        curve_data_=_poly_curve([1.0, 2.0, 3.0]),
        recorded_data={"x": [0.1, 0.2], "y": [0.3, 0.4]},
        ir_led_intensity=1.23,
        angle="90",
        pd_channel="2",
    )

    # 2. Save to disk
    od_cal.save_to_disk_for_device("od90")
    # The calibration file should now exist in .pioreactor/storage/calibrations/od90/

    # 3. Load from disk
    loaded_cal = load_calibration("od90", "my_test_cal")
    assert isinstance(loaded_cal, OD600Calibration)
    assert loaded_cal.calibration_name == "my_test_cal"
    assert loaded_cal.angle == "90"
    assert loaded_cal.curve_data_ == _poly_curve([1.0, 2.0, 3.0])

    # 4. Set as active
    od_cal.set_as_active_calibration_for_device("od90")

    # 5. Load via load_active_calibration
    active_cal = load_active_calibration("od90")
    assert isinstance(active_cal, OD600Calibration)
    assert active_cal.calibration_name == "my_test_cal"


def test_load_calibration_missing_file(temp_calibration_dir) -> None:
    with pytest.raises(FileNotFoundError):
        load_calibration("od90", "non_existent_cal")


def test_load_active_calibration_none(temp_calibration_dir) -> None:
    # Make sure 'od90' key is not set in local_persistent_storage("active_calibrations")
    with local_persistent_storage("active_calibrations") as store:
        store.pop("od90", None)

    cal = load_active_calibration("od90")
    assert cal is None


def test_load_calibration_validation_error(temp_calibration_dir) -> None:
    # 1. Create the directory for "od90" calibrations
    od_dir = temp_calibration_dir / "od90"
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
        load_calibration("od90", "bad_cal")

    assert "Error reading bad_cal" in str(exc_info.value)


# test calibration structs


@pytest.fixture
def calibration():
    return CalibrationBase(
        calibration_name="test_calibration",
        calibrated_on_pioreactor_unit="unit1",
        created_at=datetime.now(),
        curve_data_=_poly_curve([2, 3, 5]),  # 5x^2 + 3x + 2
        x="voltage",
        y="od600",
        recorded_data={"x": [0.1, 0.2, 0.3], "y": [1.0, 2.0, 3.0]},
    )


def test_predict_linear(calibration) -> None:
    calibration.curve_data_ = _poly_curve([3, 2])  # 3x + 2
    x = 4
    expected_y = 3 * x + 2
    assert calibration.x_to_y(x) == expected_y


def test_predict_quadratic(calibration) -> None:
    calibration.curve_data_ = _poly_curve([5, 3, 2])  # 5x^2 + 3x + 2
    x = 2
    expected_y = 5 * x**2 + 3 * x + 2
    assert calibration.x_to_y(x) == expected_y


def test_ipredict_linear(calibration) -> None:
    calibration.curve_data_ = _poly_curve([3, 2])  # 3x + 2
    y = 14
    expected_x = (y - 2) / 3
    assert calibration.y_to_x(y) == pytest.approx(expected_x)


def test_ipredict_quadratic_single_solution(calibration) -> None:
    calibration.curve_data_ = _poly_curve([5, 3, 2])  # 5x^2 + 3x + 2
    calibration.recorded_data = {"x": [0, 2], "y": [2, 20]}
    y = 12
    expected_x = 1.145683229480096  # Solves 5x^2 + 3x + 2 = 12
    assert calibration.y_to_x(y) == pytest.approx(expected_x)


def test_ipredict_no_solution(calibration) -> None:
    calibration.curve_data_ = _poly_curve([1, 0, 5])  # x^2 + 5, no solution for y = -10
    with pytest.raises(exc.NoSolutionsFoundError):
        calibration.y_to_x(-10)


def test_ipredict_multiple_solutions(calibration) -> None:
    calibration.curve_data_ = _poly_curve([1, 0, -6])  # x^2 - 6, solutions for y=0 are +- 2.45
    calibration.recorded_data = {"x": [0, 3], "y": [0, 9]}
    y = 0
    assert calibration.y_to_x(y) == pytest.approx(2.44948974)


def test_ipredict_solution_below_domain(calibration) -> None:
    calibration.curve_data_ = _poly_curve([5, 3, 2])  # 5x^2 + 3x + 2
    calibration.recorded_data = {"x": [0, 1], "y": [10, 20]}
    y = 1.99  # Solution below domain
    with pytest.raises(exc.SolutionBelowDomainError):
        calibration.y_to_x(y, enforce_bounds=True)


def test_ipredict_solution_above_domain(calibration) -> None:
    calibration.curve_data_ = _poly_curve([25, -10, 1])  # 25x^2 - 10x + 1
    calibration.recorded_data = {"x": [0, 1], "y": [0, 100]}
    y = 50  # Solution above domain
    with pytest.raises(exc.SolutionAboveDomainError):
        calibration.y_to_x(y, enforce_bounds=True)


def test_ipredict_zero_solution_in_domain_for_od45_reference_calibration() -> None:
    calibration_data = ODCalibration(
        calibration_name="od45-optical-reference-standard-2026-01-08",
        calibrated_on_pioreactor_unit="lw1209",
        created_at=datetime(2026, 1, 8, 14, 56, 49, 692000, tzinfo=timezone.utc),
        curve_data_=_poly_curve([1.4383526269350404, 8.038873388460928e-14]),
        recorded_data={"x": [0, 1000], "y": [0, 1438.3526269350407]},
        ir_led_intensity=80,
        angle="45",
        pd_channel="1",
    )

    assert calibration_data.y_to_x(0.0, enforce_bounds=True) == 0.0


def test_predict_ipredict_consistency(calibration) -> None:
    calibration.curve_data_ = _poly_curve([2, -3, 1])  # 2x^2 - 3x + 1
    calibration.recorded_data = {"x": [0, 3], "y": [1, 16]}
    x = 2
    y = calibration.x_to_y(x)
    assert calibration.y_to_x(y) == pytest.approx(x)


def test_spline_predict_linear() -> None:
    from pioreactor.utils.splines import spline_fit

    x = [0.0, 2.0]
    y = [1.0, 5.0]
    spline_data = spline_fit(x, y, knots=2)
    calibration = CalibrationBase(
        calibration_name="test_spline_calibration",
        calibrated_on_pioreactor_unit="unit1",
        created_at=datetime.now(),
        curve_data_=spline_data,
        x="voltage",
        y="od600",
        recorded_data={"x": x, "y": y},
    )

    assert calibration.x_to_y(1.0) == pytest.approx(3.0)


def test_spline_ipredict_linear() -> None:
    from pioreactor.utils.splines import spline_fit

    x = [0.0, 2.0]
    y = [1.0, 5.0]
    spline_data = spline_fit(x, y, knots=2)
    calibration = CalibrationBase(
        calibration_name="test_spline_calibration",
        calibrated_on_pioreactor_unit="unit1",
        created_at=datetime.now(),
        curve_data_=spline_data,
        x="voltage",
        y="od600",
        recorded_data={"x": x, "y": y},
    )

    assert calibration.y_to_x(3.0) == pytest.approx(1.0)


def test_linear_data_produces_linear_curve_in_range_even_if_high_degree() -> None:
    od = np.sort(
        np.r_[
            2 ** np.linspace(np.log2(0.5), np.log2(1), num=10),
            2 ** np.linspace(np.log2(0.25), np.log2(0.5), num=10),
            2 ** np.linspace(np.log2(0.125), np.log2(0.25), num=10),
        ]
    )

    od = np.insert(od, 0, 0)
    v = 0.5 * od + 0.005 * np.random.randn(od.shape[0])

    n = len(v)
    weights = [1.0] * n
    weights[0] = n / 2

    curve_data_ = calculate_poly_curve_of_best_fit(od, v, degree=4, weights=weights)  # type: ignore
    curve_callable = curve_to_callable(curve_data_)
    for od_ in od:
        assert (curve_callable(od_) - od_ * 0.5) < 0.035


def test_mandys_data_for_pathological_poly() -> None:
    # https://forum.pioreactor.com/t/very-low-od-readings-map-to-max/630/5
    od = [0.0, 0.139, 0.155, 0.378, 0.671, 0.993, 1.82, 4.061]
    v = [0.0, 0.0158, 0.0322, 0.0589, 0.1002, 0.1648, 0.4045, 0.5463]

    n = len(v)
    weights = [1.0] * n
    weights[0] = n / 2

    curve_data_ = calculate_poly_curve_of_best_fit(od, v, degree=3, weights=weights)  # type: ignore
    curve_callable = curve_to_callable(curve_data_)
    assert abs(curve_callable(0.002) - 0.002) < 0.1

    mcal = OD600Calibration(
        calibration_name="mandy",
        calibrated_on_pioreactor_unit="pio1",
        created_at=current_utc_datetime(),
        curve_data_=curve_data_,
        recorded_data={"x": od, "y": v},
        ir_led_intensity=70.0,
        angle="90",
        pd_channel="2",
    )

    assert abs(mcal.x_to_y(0.002) - curve_callable(0.002)) < 1e-10
    assert abs(mcal.y_to_x(0.002) - 0.002) < 0.1


def test_custom_protocol() -> None:
    class CustomOD600CalibrationProtocol(CalibrationProtocol):
        protocol_name = "custom"
        target_device = "od90"

        @staticmethod
        def run(target_device, **kwargs):
            pass

    assert get_calibration_protocols()["od90"]["custom"].__name__ == "CustomOD600CalibrationProtocol"

    class CustomCalibrationProtocolWithList(CalibrationProtocol):
        protocol_name = "custom"
        target_device = ["A", "B", "C"]

        @staticmethod
        def run(target_device, **kwargs):
            pass

    protocols = get_calibration_protocols()
    assert protocols["A"]["custom"].__name__ == "CustomCalibrationProtocolWithList"
    assert protocols["B"]["custom"].__name__ == "CustomCalibrationProtocolWithList"
    assert protocols["C"]["custom"].__name__ == "CustomCalibrationProtocolWithList"
