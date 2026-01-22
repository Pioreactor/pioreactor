# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from pioreactor import structs
from pioreactor.utils.od_fusion import compute_fused_od
from pioreactor.utils.od_fusion import fit_fusion_model
from pioreactor.utils.od_fusion import FUSION_ANGLES
from pioreactor.utils.timing import current_utc_datetime


def _load_angle_dataset() -> list[dict[str, str]]:
    dataset_path = Path(__file__).parent / "data" / "od_angle_dataset_original.csv"
    with dataset_path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _build_calibration_from_records(records: list[tuple[str, float, float]]) -> structs.ODFusionCalibration:
    fit = fit_fusion_model(records)
    return structs.ODFusionCalibration(
        created_at=current_utc_datetime(),
        calibrated_on_pioreactor_unit="test_unit",
        calibration_name="test_fusion",
        curve_data_=fit.mu_splines["90"],
        curve_type="spline",
        recorded_data=fit.recorded_data,
        ir_led_intensity=80.0,
        angles=list(FUSION_ANGLES),
        mu_splines=fit.mu_splines,
        sigma_splines_log=fit.sigma_splines_log,
        min_logc=fit.min_logc,
        max_logc=fit.max_logc,
        sigma_floor=fit.sigma_floor,
    )


def test_fusion_model_predicts_expected_concentration_range() -> None:
    rows = _load_angle_dataset()
    instrument = "1"
    records: list[tuple[str, float, float]] = []

    for row in rows:
        if row["instrument_number"] != instrument:
            continue
        angle = row["angle"]
        if angle not in FUSION_ANGLES:
            continue
        concentration = float(row["concentration_mg_ml"])
        reading = float(row["od_reading"])
        if concentration <= 0.0 or reading <= 0.0:
            continue
        records.append((angle, concentration, reading))

    calibration = _build_calibration_from_records(records)

    by_vial: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    vial_concentrations: dict[str, float] = {}
    for row in rows:
        if row["instrument_number"] != instrument:
            continue
        angle = row["angle"]
        if angle not in FUSION_ANGLES:
            continue
        concentration = float(row["concentration_mg_ml"])
        if concentration <= 0.0:
            continue
        vial_concentrations[row["vial_number"]] = concentration
        by_vial[row["vial_number"]].setdefault(angle, []).append(float(row["od_reading"]))

    max_concentration = 3.2
    max_relative_error = 0.15
    checked = 0

    for vial_number in sorted(by_vial, key=lambda v: int(v)):
        data = by_vial[vial_number]
        concentration = vial_concentrations[vial_number]
        if concentration > max_concentration:
            continue

        readings_by_angle: dict[str, float] = {}
        missing = False
        for angle in FUSION_ANGLES:
            values = data.get(angle)
            if not values:
                missing = True
                break
            readings_by_angle[angle] = sum(values) / len(values)  # type: ignore[arg-type]
        if missing:
            continue

        fused = compute_fused_od(calibration, readings_by_angle)
        relative_error = abs(fused - concentration) / concentration
        assert relative_error <= max_relative_error
        checked += 1

    assert checked >= 5
