# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from pioreactor.calibrations.pooling import pool_od_calibrations
from pioreactor.calibrations.pooling import _POOLING_HANDLERS
from pioreactor.structs import OD600Calibration
from pioreactor.utils.timing import current_utc_datetime


def make_od_calibration(
    name: str, 
    x: list[float], 
    y: list[float], 
    angle: str = "90", 
    pd_channel: str = "1",
    ir_led_intensity: float = 50.0
) -> OD600Calibration:
    return OD600Calibration(
        created_at=current_utc_datetime(),
        calibrated_on_pioreactor_unit="worker1",
        calibration_name=name,
        angle=angle,
        pd_channel=pd_channel,
        ir_led_intensity=ir_led_intensity,
        curve_data_={"type": "spline", "knots": [], "coefficients": []}, # type: ignore
        recorded_data={"x": x, "y": y}
    )


def test_pool_two_od_calibrations_merges_recorded_data():
    cal1 = make_od_calibration("cal1", [1.0, 2.0], [10.0, 20.0])
    cal2 = make_od_calibration("cal2", [3.0, 4.0], [30.0, 40.0])
    
    pooled = pool_od_calibrations([cal1, cal2], fit="poly")
    assert pooled.calibrated_on_pioreactor_unit == "$cluster"
    assert pooled.calibration_name.startswith("pooled-od90")
    
    # Check that x and y points from both donors are present
    assert len(pooled.recorded_data["x"]) == 4
    assert set(pooled.recorded_data["x"]) == {1.0, 2.0, 3.0, 4.0}
    assert set(pooled.recorded_data["y"]) == {10.0, 20.0, 30.0, 40.0}
    
    # Check the curve_data_ has been refit (using poly for simpler test)
    from pioreactor.structs import PolyFitCoefficients
    assert isinstance(pooled.curve_data_, PolyFitCoefficients)


def test_pool_calibrations_rejects_mismatched_angles():
    cal1 = make_od_calibration("cal1", [1.0], [10.0], angle="90")
    cal2 = make_od_calibration("cal2", [2.0], [20.0], angle="135")
    
    with pytest.raises(ValueError, match="Incompatible angles"):
        pool_od_calibrations([cal1, cal2])


def test_pool_calibrations_rejects_mismatched_pd_channels():
    cal1 = make_od_calibration("cal1", [1.0], [10.0], pd_channel="1")
    cal2 = make_od_calibration("cal2", [2.0], [20.0], pd_channel="2")
    
    with pytest.raises(ValueError, match="Incompatible pd_channels"):
        pool_od_calibrations([cal1, cal2])


def test_pool_calibrations_rejects_incompatible_ir_intensity():
    cal1 = make_od_calibration("cal1", [1.0], [10.0], ir_led_intensity=50.0)
    cal2 = make_od_calibration("cal2", [2.0], [20.0], ir_led_intensity=55.0) # > 5% difference
    
    with pytest.raises(ValueError, match="Incompatible ir_led_intensity"):
        pool_od_calibrations([cal1, cal2])
        
        
def test_pool_calibrations_accepts_compatible_ir_intensity():
    cal1 = make_od_calibration("cal1", [1.0], [10.0], ir_led_intensity=50.0)
    cal2 = make_od_calibration("cal2", [2.0], [20.0], ir_led_intensity=51.0) # <= 5% difference
    
    pooled = pool_od_calibrations([cal1, cal2], fit="poly")
    assert len(pooled.recorded_data["x"]) == 2


def test_pool_single_calibration():
    cal1 = make_od_calibration("cal1", [1.0], [10.0])
    
    pooled = pool_od_calibrations([cal1])
    assert "from-1-unit" in pooled.calibration_name
    assert pooled.calibrated_on_pioreactor_unit == "$cluster"
    assert len(pooled.recorded_data["x"]) == 1


def test_extension_point_registry_is_accessible():
    assert "od" in _POOLING_HANDLERS
    assert "od600" in _POOLING_HANDLERS
    assert _POOLING_HANDLERS["od"] == pool_od_calibrations
