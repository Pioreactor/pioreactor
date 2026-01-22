# -*- coding: utf-8 -*-
from __future__ import annotations

from os import environ
from pathlib import Path

from msgspec import yaml


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float))


def _coerce_float_list(values: list[object]) -> list[float]:
    return [float(value) for value in values if _is_number(value)]


def _coerce_float_matrix(values: list[object]) -> list[list[float]]:
    matrix: list[list[float]] = []
    for row in values:
        if isinstance(row, list):
            matrix.append([float(item) for item in row if _is_number(item)])
    return matrix


def _infer_curve_type(curve_data: list[object]) -> str:
    if len(curve_data) == 2 and isinstance(curve_data[0], list) and isinstance(curve_data[1], list):
        return "spline"
    return "poly"


def _migrate_curve_data(data: dict) -> bool:
    curve_data = data.get("curve_data_")
    curve_type = data.get("curve_type")

    save_again = False

    if "curve_type" in data:
        del data["curve_type"]
        save_again = True

    if isinstance(curve_data, list):
        if curve_type is None:
            curve_type = _infer_curve_type(curve_data)
        elif curve_type == "poly":
            data["curve_data_"] = {
                "type": "poly",
                "coefficients": _coerce_float_list(curve_data),
            }
            save_again = True
        elif curve_type == "spline":
            knots: list[float] = []
            coefficients: list[list[float]] = []
            if len(curve_data) == 2 and isinstance(curve_data[0], list) and isinstance(curve_data[1], list):
                knots = _coerce_float_list(curve_data[0])
                coefficients = _coerce_float_matrix(curve_data[1])
            data["curve_data_"] = {
                "type": "spline",
                "knots": knots,
                "coefficients": coefficients,
            }
            save_again = True

    return save_again


def main() -> None:
    dot_pioreactor = environ.get("DOT_PIOREACTOR", "/home/pioreactor/.pioreactor")
    calibration_dir = Path(dot_pioreactor) / "storage" / "calibrations"
    if not calibration_dir.exists():
        return

    updated_files = 0
    for yaml_file in calibration_dir.rglob("*.yaml"):
        try:
            data = yaml.decode(yaml_file.read_bytes())
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        if _migrate_curve_data(data):
            yaml_file.write_bytes(yaml.encode(data))
            updated_files += 1

    print(f"Migrated calibration curve data in {updated_files} file(s).")


if __name__ == "__main__":
    main()
