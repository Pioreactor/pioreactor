# -*- coding: utf-8 -*-
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest
from msgspec import ValidationError
from msgspec.yaml import decode
from msgspec.yaml import encode
from pioreactor import calibrations
from pioreactor import exc
from pioreactor import structs
from pioreactor.calibrations.refit import refit_calibration
from pioreactor.utils.akimas import akima_fit
from pioreactor.utils.splines import spline_fit
from pioreactor.web import tasks


def example() -> structs.SimplePeristalticPumpCalibration:
    return structs.SimplePeristalticPumpCalibration(
        calibration_name="inclusion-test",
        calibrated_on_pioreactor_unit="unit1",
        created_at=datetime.now(timezone.utc),
        curve_data_=structs.PolyFitCoefficients(coefficients=[1.0, 0.0]),
        recorded_data={"x": [0.0, 1.1234567890123, 2.0, 3.0], "y": [0.0, 1.1234567890123, 2.0, 40.0]},
        hz=250,
        dc=60,
        voltage=5,
    )


@pytest.mark.parametrize("family", ["poly", "spline", "akima"])
def test_exclude_restore_and_reproduce(family: str) -> None:
    original = example()
    if family == "spline":
        original.curve_data_ = spline_fit(original.recorded_data["x"], original.recorded_data["y"], knots=2)
    elif family == "akima":
        original.curve_data_ = akima_fit(original.recorded_data["x"], original.recorded_data["y"])
    candidate = refit_calibration(original, [True, True, True, False])
    assert candidate.recorded_data == original.recorded_data
    assert original.included is None
    assert candidate.x_to_y(1.0) == pytest.approx(1.0)
    restored = decode(encode(candidate), type=structs.SimplePeristalticPumpCalibration)
    assert restored == candidate
    assert refit_calibration(restored, restored.included).curve_data_ == restored.curve_data_
    with pytest.raises(exc.SolutionAboveDomainError):
        candidate.y_to_x(2.5, enforce_bounds=True)
    reincluded = refit_calibration(candidate, [True] * 4)
    assert reincluded.recorded_data == original.recorded_data
    assert reincluded.x_to_y(3.0) > candidate.x_to_y(3.0)


@pytest.mark.parametrize("mask", [[True], [True, True, True, 1], [False] * 4, [True, False, False, False]])
def test_invalid_fit_does_not_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mask: list[bool]
) -> None:
    monkeypatch.setattr(calibrations, "CALIBRATION_PATH", tmp_path)
    original = example()
    path = Path(original.save_to_disk_for_device("media_pump"))
    previous = path.read_bytes()
    with pytest.raises(ValueError):
        tasks.update_calibration_measurements.call_local("media_pump", original.calibration_name, mask)
    assert path.read_bytes() == previous


def test_legacy_load_and_task_save_preserve_inactive_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(calibrations, "CALIBRATION_PATH", tmp_path)
    original = example()
    path = Path(original.save_to_disk_for_device("media_pump"))
    path.write_bytes(path.read_bytes().replace(b"included: null\n", b""))
    loaded = calibrations.load_calibration("media_pump", original.calibration_name)
    assert loaded.included is None
    assert loaded.curve_data_ == original.curve_data_
    result = tasks.update_calibration_measurements.call_local(
        "media_pump", original.calibration_name, [True, True, True, False]
    )
    assert result["is_active"] is False
    saved = calibrations.load_calibration("media_pump", original.calibration_name)
    assert saved.included == [True, True, True, False]
    assert saved.recorded_data == original.recorded_data
    assert saved.created_at == original.created_at


def test_failed_atomic_replace_preserves_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(calibrations, "CALIBRATION_PATH", tmp_path)
    original = example()
    path = Path(original.save_to_disk_for_device("media_pump"))
    previous = path.read_bytes()
    candidate = refit_calibration(original, [True, True, True, False])

    def fail_replace(self: Path, target: Path) -> None:
        raise OSError("disk error")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="disk error"):
        candidate.save_to_disk_for_device("media_pump")
    assert path.read_bytes() == previous
    assert list(path.parent.glob(".calibration-*")) == []


def test_decode_rejects_misaligned_mask() -> None:
    payload = encode(example()).replace(b"included: null", b"included: [true]")
    with pytest.raises(ValidationError, match="one boolean"):
        decode(payload, type=structs.SimplePeristalticPumpCalibration)


def test_runtime_clamping_uses_only_included_measurements() -> None:
    from pioreactor.background_jobs.od_reading import CachedCalibrationTransformer

    cal = structs.OD600Calibration(
        calibration_name="masked-extrema",
        calibrated_on_pioreactor_unit="unit1",
        created_at=datetime.now(timezone.utc),
        curve_data_=structs.PolyFitCoefficients(coefficients=[1.0]),
        angle="90",
        pd_channel="2",
        ir_led_intensity=50.0,
        recorded_data={"x": [0.0, 2.0, 100.0], "y": [1.0, 0.5, 200.0]},
        included=[True, True, False],
    )
    transformer = CachedCalibrationTransformer()
    transformer.hydate_models(cal)
    assert transformer.models["2"](201.0) == pytest.approx(0.0)
    assert transformer.models["2"](-1.0) == pytest.approx(2.0)


def test_constant_polynomial_retains_degree() -> None:
    cal = example()
    cal.curve_data_ = structs.PolyFitCoefficients(coefficients=[1.0])
    result = refit_calibration(cal, [True, True, True, False])
    assert len(result.curve_data_.coefficients) == 1
    assert result.x_to_y(0.0) == pytest.approx(sum(cal.recorded_data["y"][:3]) / 3)


def test_spline_rejects_underdetermined_fit_despite_enough_rows() -> None:
    cal = example()
    cal.recorded_data = {"x": [float(x) for x in range(11)], "y": [float(x) for x in range(11)]}
    cal.curve_data_ = spline_fit(
        cal.recorded_data["x"], cal.recorded_data["y"], knots=[0.0, 1.0, 2.0, 3.0, 4.0, 10.0]
    )
    with pytest.raises(ValueError, match="knot range"):
        refit_calibration(cal, [False] * 5 + [True] * 6)


@pytest.mark.parametrize("family", ["poly", "spline", "akima"])
def test_correct_y_values_and_reproduce(family: str) -> None:
    original = example()
    if family == "spline":
        original.curve_data_ = spline_fit(original.recorded_data["x"], original.recorded_data["y"], knots=2)
    elif family == "akima":
        original.curve_data_ = akima_fit(original.recorded_data["x"], original.recorded_data["y"])
    values = [2 * value for value in original.recorded_data["x"]]
    values[-1] = 123.456789012345
    candidate = refit_calibration(original, [True, True, True, False], values)
    assert candidate.recorded_data["x"] == original.recorded_data["x"]
    assert candidate.recorded_data["y"] == values
    assert original.recorded_data["y"][-1] == 40.0
    assert candidate.x_to_y(1.0) == pytest.approx(2.0)
    saved = decode(encode(candidate), type=structs.SimplePeristalticPumpCalibration)
    assert refit_calibration(saved, saved.included).curve_data_ == candidate.curve_data_


@pytest.mark.parametrize("values", [[1.0], [0.0, 1.0, 2.0, float("nan")], [0.0, 1.0, 2.0, float("inf")]])
def test_invalid_y_values_leave_saved_calibration_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, values: list[float]
) -> None:
    monkeypatch.setattr(calibrations, "CALIBRATION_PATH", tmp_path)
    original = example()
    path = Path(original.save_to_disk_for_device("media_pump"))
    previous = path.read_bytes()
    with pytest.raises(ValueError):
        tasks.update_calibration_measurements.call_local(
            "media_pump", original.calibration_name, [True, True, True, False], values
        )
    assert path.read_bytes() == previous


@pytest.mark.parametrize("family", ["poly", "spline", "akima"])
def test_correct_both_axes_and_reproduce(family: str) -> None:
    original = example()
    if family == "spline":
        original.curve_data_ = spline_fit(original.recorded_data["x"], original.recorded_data["y"], knots=2)
    elif family == "akima":
        original.curve_data_ = akima_fit(original.recorded_data["x"], original.recorded_data["y"])
    x = [10.1234567890123, 20.0, 30.0, 40.0]
    y = [2 * value for value in x]
    candidate = refit_calibration(original, [True, True, True, False], y_values=y, x_values=x)
    assert candidate.recorded_data == {"x": x, "y": y}
    assert original.recorded_data["x"][0] == 0.0
    assert candidate.x_to_y(15.0) == pytest.approx(30.0)
    saved = decode(encode(candidate), type=structs.SimplePeristalticPumpCalibration)
    assert saved.recorded_data == candidate.recorded_data
    assert refit_calibration(saved, saved.included).curve_data_ == candidate.curve_data_


@pytest.mark.parametrize("x", [[1.0], [1.0, 1.0, 1.0, 1.0], [0.0, 1.0, 2.0, float("inf")]])
def test_invalid_x_edits_do_not_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, x: list[float]
) -> None:
    monkeypatch.setattr(calibrations, "CALIBRATION_PATH", tmp_path)
    original = example()
    path = Path(original.save_to_disk_for_device("media_pump"))
    previous = path.read_bytes()
    with pytest.raises(ValueError):
        tasks.update_calibration_measurements.call_local(
            "media_pump", original.calibration_name, [True, True, True, False], x_values=x
        )
    assert path.read_bytes() == previous
