# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import math
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Callable
from typing import cast

import pytest
from pioreactor import structs
from pioreactor.structs import CalibrationBase
from pioreactor.utils.polys import poly_eval
from pioreactor.utils.polys import poly_fit
from pioreactor.utils.splines import spline_eval
from pioreactor.utils.splines import spline_fit

CurveData = tuple[str, str, str, list[float], list[float]]
FitFunc = Callable[[list[float], list[float]], structs.CalibrationCurveData]
EvalFunc = Callable[[structs.CalibrationCurveData, float], float]


def _load_od_angle_curves(dataset_path: Path) -> list[CurveData]:
    curves: dict[tuple[str, str, str], list[tuple[float, float]]] = {}
    with dataset_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            angle = row["angle"]
            if angle == "180":
                continue
            key = (row["instrument_number"], angle, row["trial_number"])
            curves.setdefault(key, []).append((float(row["od_reading"]), float(row["concentration_mg_ml"])))

    curve_data: list[CurveData] = []
    for (instrument_number, angle, trial_number), values in sorted(curves.items()):
        xs = [x for x, _ in values]
        ys = [y for _, y in values]
        curve_data.append((instrument_number, angle, trial_number, xs, ys))

    return curve_data


DATASET_PATH = Path(__file__).resolve().parent / "data/od_angle_dataset_original.csv"
CURVES = _load_od_angle_curves(DATASET_PATH)


def _fit_poly(xs: list[float], ys: list[float]) -> structs.PolyFitCoefficients:
    return poly_fit(xs, ys, degree="auto")


def _fit_spline(xs: list[float], ys: list[float]) -> structs.SplineFitData:
    return spline_fit(xs, ys, knots="auto")


def _eval_poly(curve_data: structs.CalibrationCurveData, x: float) -> float:
    return poly_eval(cast(structs.PolyFitCoefficients, curve_data), x)


def _eval_spline(curve_data: structs.CalibrationCurveData, x: float) -> float:
    return spline_eval(cast(structs.SplineFitData, curve_data), x)


FITTERS: list[tuple[str, FitFunc]] = [
    ("poly", _fit_poly),
    ("spline", _fit_spline),
]


EVALUATORS: dict[str, EvalFunc] = {
    "poly": _eval_poly,
    "spline": _eval_spline,
}


def _curve_id(curve: CurveData) -> str:
    instrument_number, angle, trial_number, _, _ = curve
    return f"inst{instrument_number}-angle{angle}-trial{trial_number}"


@pytest.mark.parametrize("curve_tag, fit_func", FITTERS, ids=[fit for fit, _ in FITTERS])
@pytest.mark.parametrize("curve", CURVES, ids=_curve_id)
def test_fit_and_eval_on_real_od_curves(curve_tag: str, fit_func: FitFunc, curve: CurveData) -> None:
    instrument_number, angle, trial_number, xs, ys = curve
    curve_data = fit_func(xs, ys)
    assert curve_data

    calibration = CalibrationBase(
        calibration_name=f"inst{instrument_number}-angle{angle}-trial{trial_number}-{curve_tag}",
        calibrated_on_pioreactor_unit="test-unit",
        created_at=datetime.now(timezone.utc),
        curve_data_=curve_data,
        x="OD",
        y="concentration_mg_ml",
        recorded_data={"x": xs, "y": ys},
    )

    x_sample = xs[len(xs) // 2]
    eval_func = EVALUATORS[curve_data.type]
    y_eval = eval_func(curve_data, x_sample)
    y_pred = calibration.x_to_y(x_sample)
    assert math.isfinite(y_eval)
    assert math.isfinite(y_pred)
    assert y_pred == pytest.approx(y_eval, abs=1e-8)

    y_min, y_max = min(ys), max(ys)
    assert y_min - 5.0 <= y_pred <= y_max + 5.0
