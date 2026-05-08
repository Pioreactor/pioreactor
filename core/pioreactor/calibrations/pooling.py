# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t
from collections.abc import Callable

from pioreactor import structs
from pioreactor.utils.timing import current_utc_datestamp
from pioreactor.utils.timing import current_utc_datetime


def pool_od_calibrations(
    calibrations: list[structs.ODCalibration | structs.OD600Calibration],
    fit: t.Literal["spline", "poly", "akima"] = "spline",
) -> structs.OD600Calibration | structs.ODCalibration:
    """
    Merge raw recorded_data from multiple OD calibrations and refit a new curve.
    """
    if not calibrations:
        raise ValueError("No calibrations provided for pooling.")

    if len(calibrations) == 1:
        # Just copy and rename
        cal = calibrations[0]
        base_class = type(cal)
        new_name = f"pooled-od{cal.angle}-from-1-unit-{current_utc_datestamp()}"

        kwargs = {f: getattr(cal, f) for f in cal.__struct_fields__}
        kwargs["calibration_name"] = new_name
        kwargs["calibrated_on_pioreactor_unit"] = "$cluster"
        kwargs["created_at"] = current_utc_datetime()
        return base_class(**kwargs)

    # Validation: must share angle and pd_channel
    first_cal = calibrations[0]
    angle = first_cal.angle
    pd_channel = first_cal.pd_channel
    ir_led_intensity = first_cal.ir_led_intensity

    # Check compatibility
    for cal in calibrations[1:]:
        if cal.angle != angle:
            raise ValueError(f"Incompatible angles: {angle} != {cal.angle}")
        if cal.pd_channel != pd_channel:
            raise ValueError(f"Incompatible pd_channels: {pd_channel} != {cal.pd_channel}")

        # ir_led_intensity must be within 5%
        if ir_led_intensity == 0:
            if cal.ir_led_intensity != 0:
                raise ValueError("Incompatible ir_led_intensity: 0 vs non-zero")
        elif abs(cal.ir_led_intensity - ir_led_intensity) / ir_led_intensity > 0.05:
            raise ValueError(
                f"Incompatible ir_led_intensity: {ir_led_intensity} and {cal.ir_led_intensity} differ by > 5%"
            )

    # Merging
    merged_x: list[float] = []
    merged_y: list[float] = []
    weights: list[float] = []

    for cal in calibrations:
        x_data = cal.recorded_data["x"]
        y_data = cal.recorded_data["y"]
        count = len(x_data)
        if count == 0:
            continue

        merged_x.extend(x_data)
        merged_y.extend(y_data)

        # Equal weight for each point
        weights.extend([1.0] * count)

    if not merged_x:
        raise ValueError("No recorded data found in any provided calibrations.")

    # Refit
    if fit == "poly":
        from pioreactor.calibrations.utils import calculate_poly_curve_of_best_fit

        curve_data = calculate_poly_curve_of_best_fit(merged_x, merged_y, degree=2, weights=weights)
    elif fit == "spline":
        from pioreactor.utils.splines import spline_fit

        knots_count = min(4, len(set(merged_x)))
        curve_data = spline_fit(merged_x, merged_y, knots=max(2, knots_count), weights=weights)  # type: ignore
    elif fit == "akima":
        from pioreactor.utils.akimas import akima_fit

        curve_data = akima_fit(merged_x, merged_y)  # type: ignore
    else:
        raise ValueError(f"Unsupported fit type: {fit}")

    new_name = f"pooled-od{angle}-{current_utc_datestamp()}"

    kwargs = {f: getattr(first_cal, f) for f in first_cal.__struct_fields__}
    kwargs["calibration_name"] = new_name
    kwargs["calibrated_on_pioreactor_unit"] = "$cluster"
    kwargs["created_at"] = current_utc_datetime()
    kwargs["curve_data_"] = curve_data
    kwargs["recorded_data"] = {"x": merged_x, "y": merged_y}

    base_class = type(first_cal)
    return base_class(**kwargs)


_POOLING_HANDLERS: dict[str, Callable] = {
    "od": pool_od_calibrations,
    "od600": pool_od_calibrations,
}
