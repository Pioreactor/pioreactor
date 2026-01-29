# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

import pytest
from pioreactor import structs
from pioreactor.calibrations.protocols import od_fusion_offset
from pioreactor.config import config


def _example_akima() -> structs.AkimaFitData:
    return structs.AkimaFitData(
        knots=[0.0, 1.0],
        coefficients=[[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]],
    )


def _example_estimator() -> structs.ODFusionEstimator:
    akima = _example_akima()
    return structs.ODFusionEstimator(
        estimator_name="base-estimator",
        calibrated_on_pioreactor_unit="unit1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ir_led_intensity=10.0,
        angles=["45"],
        mu_splines={"45": akima},
        sigma_splines_log={"45": akima},
        min_logc=0.1,
        max_logc=1.2,
        sigma_floor=0.01,
        recorded_data={"base": "data"},
    )


def test_affine_transform_cubic_fit_data_scales_knots_and_coeffs() -> None:
    akima = _example_akima()

    transformed = od_fusion_offset._affine_transform_cubic_fit_data(akima, scale_logc=2.0, offset_logc=1.0)

    assert transformed.knots == [1.0, 3.0]
    assert transformed.coefficients == [
        [1.0, 1.0, 0.75, 0.5],
        [5.0, 3.0, 1.75, 1.0],
    ]


def test_affine_transform_cubic_fit_data_rejects_non_positive_scale() -> None:
    akima = _example_akima()

    with pytest.raises(ValueError, match="Scale must be positive"):
        od_fusion_offset._affine_transform_cubic_fit_data(akima, scale_logc=0.0, offset_logc=1.0)


def test_apply_logc_affine_to_estimator_applies_transform() -> None:
    estimator = _example_estimator()

    updated = od_fusion_offset._apply_logc_affine_to_estimator(
        estimator,
        estimator_name="updated",
        calibrated_on_unit="unit2",
        scale_logc=2.0,
        offset_logc=1.0,
        standards=[{"od": 0.3}],
        source_unit="unit1",
        source_estimator_name="base-estimator",
    )

    assert updated.estimator_name == "updated"
    assert updated.calibrated_on_pioreactor_unit == "unit2"
    assert updated.min_logc == pytest.approx(1.2)
    assert updated.max_logc == pytest.approx(3.4)
    assert updated.angles == ["45"]
    assert updated.mu_splines["45"].knots == [1.0, 3.0]
    assert updated.sigma_splines_log["45"].knots == [1.0, 3.0]

    recorded_data = updated.recorded_data
    assert recorded_data["base_recorded_data"] == {"base": "data"}
    assert recorded_data["standards"] == [{"od": 0.3}]

    transform: dict[str, Any] = recorded_data["transform"]
    assert transform["type"] == "logc_affine"
    assert transform["scale_logc"] == 2.0
    assert transform["offset_logc"] == 1.0
    assert transform["source_unit"] == "unit1"
    assert transform["source_estimator_name"] == "base-estimator"
    assert transform["source_ir_led_intensity"] == 10.0

    assert updated.ir_led_intensity == config.getfloat("od_reading.config", "ir_led_intensity")
