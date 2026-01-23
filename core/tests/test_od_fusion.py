# -*- coding: utf-8 -*-
import csv
from collections import defaultdict
from pathlib import Path
from typing import cast

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.utils.od_fusion import compute_fused_od
from pioreactor.utils.od_fusion import fit_fusion_model
from pioreactor.utils.od_fusion import FUSION_ANGLES
from pioreactor.utils.timing import current_utc_datetime


def _load_angle_dataset() -> list[dict[str, str]]:
    dataset_path = Path(__file__).parent / "data" / "od_angle_dataset_original.csv"
    with dataset_path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _records_for_instrument(instrument: str) -> list[tuple[pt.PdAngle, float, float]]:
    records: list[tuple[pt.PdAngle, float, float]] = []
    for row in _load_angle_dataset():
        if row["instrument_number"] != instrument:
            continue
        angle = row["angle"]
        if angle not in FUSION_ANGLES:
            continue
        angle_literal = cast(pt.PdAngle, angle)
        concentration = float(row["concentration_mg_ml"])
        reading = float(row["od_reading"])
        if concentration <= 0.0 or reading <= 0.0:
            continue
        records.append((angle_literal, concentration, reading))
    return records


def _build_estimator_from_records(records: list[tuple[str, float, float]]) -> structs.ODFusionEstimator:
    fit = fit_fusion_model(records)  # type: ignore
    return structs.ODFusionEstimator(
        created_at=current_utc_datetime(),
        calibrated_on_pioreactor_unit="test_unit",
        estimator_name="test_fusion",
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
    records = _records_for_instrument(instrument)
    calibration = _build_estimator_from_records(records)  # type: ignore

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

        readings_by_angle: dict[pt.PdAngle, float] = {}
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
        assert isinstance(fused, float)
        relative_error = abs(fused - concentration) / concentration
        assert relative_error <= max_relative_error
        checked += 1

    assert checked >= 5


def test_estimator_roundtrip_save_and_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

    import pioreactor.estimators as estimators_module

    estimator = _build_estimator_from_records(_records_for_instrument("1"))  # type: ignore
    saved_path = estimators_module.save_estimator(pt.OD_FUSED_DEVICE, estimator)
    assert estimator.estimator_name in saved_path

    loaded = estimators_module.load_estimator(pt.OD_FUSED_DEVICE, estimator.estimator_name)
    assert isinstance(loaded, structs.ODFusionEstimator)
    assert loaded.estimator_name == estimator.estimator_name
    assert loaded.angles == estimator.angles

    estimators_module.set_active_estimator(pt.OD_FUSED_DEVICE, estimator.estimator_name)
    active = estimators_module.load_active_estimator(pt.OD_FUSED_DEVICE)
    assert active is not None
    assert active.estimator_name == estimator.estimator_name

    estimators = estimators_module.list_of_estimators_by_device(pt.OD_FUSED_DEVICE)
    assert estimator.estimator_name in estimators
