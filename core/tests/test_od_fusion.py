# -*- coding: utf-8 -*-
import csv
from collections import defaultdict
from pathlib import Path
from typing import cast

import pytest
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


def _records_for_instrument(instrument: str) -> list[tuple[pt.PdAngle, float, pt.Voltage]]:
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


def _aggregate_obs_for_instrument(
    instrument: str,
) -> tuple[dict[str, dict[pt.PdAngle, list[float]]], dict[str, float]]:
    obs_by_vial: dict[str, dict[pt.PdAngle, list[float]]] = defaultdict(
        lambda: {angle: [] for angle in FUSION_ANGLES}
    )
    vial_concentrations: dict[str, float] = {}

    for row in _load_angle_dataset():
        if row["instrument_number"] != instrument:
            continue
        angle = row["angle"]
        if angle not in FUSION_ANGLES:
            continue
        vial_number = row["vial_number"]
        concentration = float(row["concentration_mg_ml"])
        reading = float(row["od_reading"])
        if concentration <= 0.0 or reading <= 0.0:
            continue
        angle_literal = cast(pt.PdAngle, angle)
        obs_by_vial[vial_number][angle_literal].append(reading)
        if vial_number not in vial_concentrations:
            vial_concentrations[vial_number] = concentration
        elif vial_concentrations[vial_number] != concentration:
            raise ValueError(f"Vial {vial_number} has inconsistent concentrations.")

    return obs_by_vial, vial_concentrations


def _build_estimator_from_records(
    records: list[tuple[pt.PdAngle, float, pt.Voltage]],
) -> structs.ODFusionEstimator:
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


@pytest.mark.parametrize(
    "instrument",
    [
        "1",
        "2",
        "3",
        "5",
        pytest.param("4", marks=pytest.mark.xfail(reason="loosey")),
    ],
)
def test_fusion_model_predicts_expected_concentration_range(instrument) -> None:

    records = _records_for_instrument(instrument)
    calibration = _build_estimator_from_records(records)  # type: ignore

    obs_by_vial, vial_concentrations = _aggregate_obs_for_instrument(instrument)
    running_max_error = 0.0
    for vial_number in obs_by_vial:
        data = obs_by_vial[vial_number]
        concentration = vial_concentrations[vial_number]

        readings_by_angle: dict[pt.PdAngle, float] = {}
        for angle in FUSION_ANGLES:
            values = data[angle]
            readings_by_angle[angle] = sum(values) / len(values)  # average for now

        fused = compute_fused_od(calibration, readings_by_angle)
        assert isinstance(fused, float)
        relative_error = abs(fused - concentration) / concentration
        running_max_error = max(running_max_error, relative_error)
    assert running_max_error < 0.1


def test_estimator_roundtrip_save_and_load(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DOT_PIOREACTOR", str(tmp_path))

    estimator = _build_estimator_from_records(_records_for_instrument("1"))  # type: ignore
    saved_path = estimator.save_to_disk_for_device(pt.OD_FUSED_DEVICE)
    assert estimator.estimator_name in saved_path

    import pioreactor.estimators as estimators_module

    loaded = estimators_module.load_estimator(pt.OD_FUSED_DEVICE, estimator.estimator_name)
    assert isinstance(loaded, structs.ODFusionEstimator)
    assert loaded.estimator_name == estimator.estimator_name
    assert loaded.angles == estimator.angles

    estimator.set_as_active_calibration_for_device(pt.OD_FUSED_DEVICE)
    active = estimators_module.load_active_estimator(pt.OD_FUSED_DEVICE)
    assert active is not None
    assert active.estimator_name == estimator.estimator_name

    estimators = estimators_module.list_of_estimators_by_device(pt.OD_FUSED_DEVICE)
    assert estimator.estimator_name in estimators
