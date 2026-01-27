# -*- coding: utf-8 -*-
import csv
from collections import defaultdict
from pathlib import Path
from typing import cast

import pytest
from msgspec.yaml import decode as yaml_decode
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
    estimator = _build_estimator_from_records(records)  # type: ignore

    obs_by_vial, vial_concentrations = _aggregate_obs_for_instrument(instrument)
    running_max_error = 0.0
    for vial_number in obs_by_vial:
        data = obs_by_vial[vial_number]
        concentration = vial_concentrations[vial_number]

        readings_by_angle: dict[pt.PdAngle, float] = {}
        for angle in FUSION_ANGLES:
            values = data[angle]
            readings_by_angle[angle] = sum(values) / len(values)  # average for now

        fused = compute_fused_od(estimator, readings_by_angle)
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


def test_fused_od_from_production_estimator() -> None:
    # HEY! This isn't actually good data, just me playing around with protocol creation.
    estimator_yaml = b"""estimator_type: od_fused_estimator
estimator_name: od-fused-estimator-2026-01-27
calibrated_on_pioreactor_unit: xr1
created_at: 2026-01-27 15:59:11.334000+00:00
ir_led_intensity: 80.0
angles:
- '45'
- '90'
- '135'
mu_splines:
  '45':
    type: spline
    knots:
    - -2.0
    - -0.3010299956639812
    - 0.0
    - 0.04139268515822507
    - 0.3010299956639812
    - 0.47712125471966244
    - 0.5440680443502757
    coefficients:
    - - -1.7438778751656192
      - 0.2441771679175396
      - 0.0
      - -0.1538559588050634
    - - -2.083549405701885
      - -1.0881380806970389
      - -0.7841899769944827
      - 30.016286698505223
    - - -1.663358237192927
      - 6.599875410448838
      - 26.323217987105046
      - -496.76889797567605
    - - -1.3803016897431428
      - 6.225629250981523
      - -35.364577783811725
      - 59.63896196983336
    - - -1.1040425955969275
      - -0.07723691500193897
      - 11.088921277796087
      - -34.888077562662275
    - - -0.9642946183295956
      - 0.5826450115599918
      - -7.3415352343282985
      - 36.554081606382624
  '90':
    type: spline
    knots:
    - -2.0
    - -0.3010299956639812
    - 0.0
    - 0.04139268515822507
    - 0.3010299956639812
    - 0.47712125471966244
    - 0.5440680443502757
    coefficients:
    - - -7.271462855489787
      - 4.203861115398141
      - 0.0
      - -0.29063465547478373
    - - -1.554523166944596
      - 1.6871111222730413
      - -1.4813386856165718
      - -0.7427775006332761
    - - -1.2011518979078963
      - 0.5933269731790018
      - -2.1521336090013854
      - -18.656239265820265
    - - -1.1816029756723165
      - 0.3192675473481794
      - -4.468829123501228
      - 4.539736203699291
    - - -1.3205028743786
      - -1.0831902713114843
      - -0.9327744284989429
      - 8.470472727379766
    - - -1.4939158140004747
      - -0.6237365213749801
      - 3.5419541935843966
      - -17.63566863139888
  '135':
    type: spline
    knots:
    - -2.0
    - -0.3010299956639812
    - 0.0
    - 0.04139268515822507
    - 0.3010299956639812
    - 0.47712125471966244
    - 0.5440680443502757
    coefficients:
    - - -4.087320030684795
      - 2.0046557348788574
      - 0.0
      - 0.1593295246050635
    - - 0.09989392556665631
      - 3.3843693113597952
      - 0.8120882493273617
      - -57.47592335512056
    - - -0.37560758142125594
      - -11.751946990566655
      - -51.09384262579841
      - 911.6601230530226
    - - -0.8849388378663108
      - -11.295779065918452
      - 62.11433870872905
      - -107.07258337855609
    - - -1.5045648912875003
      - -0.6951603391589078
      - -21.285774023205825
      - 70.67344004799358
    - - -1.9011132082364288
      - -1.6172838635511986
      - 16.04915109633636
      - -79.90998614914638
sigma_splines_log:
  '45':
    type: spline
    knots:
    - -2.0
    - 0.04139268515822507
    - 0.5440680443502757
    coefficients:
    - - -3.2188758248682015
      - -4.962468504112714e-17
      - 0.0
      - 6.411057043773277e-17
    - - -3.218875824868201
      - 7.51876196481863e-16
      - 3.9262454859872643e-16
      - -2.603566041973169e-16
  '90':
    type: spline
    knots:
    - -2.0
    - 0.04139268515822507
    - 0.5440680443502757
    coefficients:
    - - -3.2188758248682015
      - -4.962468504112714e-17
      - 0.0
      - 6.411057043773277e-17
    - - -3.218875824868201
      - 7.51876196481863e-16
      - 3.9262454859872643e-16
      - -2.603566041973169e-16
  '135':
    type: spline
    knots:
    - -2.0
    - 0.04139268515822507
    - 0.5440680443502757
    coefficients:
    - - -3.2188758248682015
      - -4.962468504112714e-17
      - 0.0
      - 6.411057043773277e-17
    - - -3.218875824868201
      - 7.51876196481863e-16
      - 3.9262454859872643e-16
      - -2.603566041973169e-16
min_logc: -2.0
max_logc: 0.5440680443502757
sigma_floor: 0.04
recorded_data:
  by_angle:
    '45':
      x:
      - -2.0
      - -0.3010299956639812
      - 0.0
      - 0.04139268515822507
      - 0.3010299956639812
      - 0.47712125471966244
      - 0.5440680443502757
      y:
      - -1.7438778751656192
      - -2.083549405701885
      - -1.663358237192927
      - -1.3803016897431428
      - -1.1040425955969275
      - -0.9642946183295956
      - -0.9472242892552836
    '90':
      x:
      - -2.0
      - -0.3010299956639812
      - 0.0
      - 0.04139268515822507
      - 0.3010299956639812
      - 0.47712125471966244
      - 0.5440680443502757
      y:
      - -7.271462855489787
      - -1.554523166944596
      - -1.2011518979078963
      - -1.1816029756723165
      - -1.3205028743786
      - -1.4939158140004747
      - -1.5250899132826319
    '135':
      x:
      - -2.0
      - -0.3010299956639812
      - 0.0
      - 0.04139268515822507
      - 0.3010299956639812
      - 0.47712125471966244
      - 0.5440680443502757
      y:
      - -4.087320030684795
      - 0.09989392556665631
      - -0.37560758142125594
      - -0.8849388378663108
      - -1.5045648912875003
      - -1.9011132082364288
      - -1.961431670006899
y: log(Voltage)
"""
    estimator = yaml_decode(estimator_yaml, type=structs.ODFusionEstimator)

    readings_by_angle: dict[pt.PdAngle, float] = {
        "45": 0.394,
        "90": 0.219,
        "135": 0.142,
    }
    fused = compute_fused_od(estimator, readings_by_angle)
    assert fused == pytest.approx(3.069325950023412, rel=0.02, abs=0.01)
