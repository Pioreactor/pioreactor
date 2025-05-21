# -*- coding: utf-8 -*-
"""
These define structs for internal data structures including MQTT messages, and are type-checkable + runtime-checked.

"""
from __future__ import annotations

import typing as t
from datetime import datetime
from pathlib import Path

from msgspec import Meta
from msgspec import Struct
from msgspec.json import encode
from msgspec.yaml import encode as yaml_encode

from pioreactor import exc
from pioreactor import types as pt
from pioreactor.logging import create_logger


T = t.TypeVar("T")


def subclass_union(cls: t.Type[T]) -> t.Type[T]:
    """
    Returns a Union of all subclasses of `cls` (excluding `cls` itself)
    Note: this can't be used in type inference...
    """

    classes = set()

    def _add(cls):
        for c in cls.__subclasses__():
            _add(c)
        classes.add(cls)

    for c in cls.__subclasses__():
        _add(c)
    return t.Union[tuple(classes)]  # type: ignore


class JSONPrintedStruct(Struct):
    def __str__(self):
        return encode(self).decode()  # this is a valid JSON str, decode() for bytes->str


class AutomationSettings(JSONPrintedStruct):
    """
    Metadata produced when settings in an automation job change
    """

    pioreactor_unit: str
    experiment: str
    started_at: t.Annotated[datetime, Meta(tz=True)]
    ended_at: t.Optional[t.Annotated[datetime, Meta(tz=True)]]
    automation_name: str
    settings: bytes


class AutomationEvent(JSONPrintedStruct, tag=True, tag_field="event_name"):  # type: ignore
    """
    Automations can return an AutomationEvent from their `execute` method, and it
    will get published to MQTT under /latest_event
    """

    message: t.Optional[str] = None
    data: t.Optional[dict] = None

    def display(self) -> str:
        if self.message:
            return f"{self.human_readable_name}: {self.message}"
        else:
            return self.human_readable_name

    @property
    def human_readable_name(self) -> str:
        name = type(self).__name__
        return name

    # @property
    # def type(self) -> str:
    #    return self.__class__.__struct_tag__  # type: ignore


class LEDChangeEvent(JSONPrintedStruct):
    """
    Produced when an LED changes value
    """

    channel: pt.LedChannel
    intensity: pt.LedIntensityValue
    source_of_event: t.Optional[str]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class DosingEvent(JSONPrintedStruct):
    """
    Output of a pump action
    """

    volume_change: float  # can be negative!
    event: str
    source_of_event: t.Optional[str]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class MeasuredRPM(JSONPrintedStruct):
    measured_rpm: t.Annotated[float, Meta(ge=0)]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class GrowthRate(JSONPrintedStruct):
    growth_rate: float
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class ODFiltered(JSONPrintedStruct):
    od_filtered: float
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class RawPDReading(JSONPrintedStruct):
    reading: pt.Voltage
    channel: pt.PdChannel


class CalibratedODReading(JSONPrintedStruct, tag=1, tag_field="calibrated"):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    angle: pt.PdAngle
    od: pt.CalibratedOD
    channel: pt.PdChannel
    calibration_name: str


class RawODReading(JSONPrintedStruct, tag=0, tag_field="calibrated"):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    angle: pt.PdAngle
    od: pt.RawOD
    channel: pt.PdChannel


ODReading = RawODReading | CalibratedODReading


class ODReadings(JSONPrintedStruct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    ods: dict[pt.PdChannel, ODReading]


class Temperature(JSONPrintedStruct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    temperature: float


class Voltage(JSONPrintedStruct):
    timestamp: t.Annotated[datetime, Meta(tz=True)]
    voltage: pt.Voltage


X = float
Y = float


class CalibrationBase(Struct, tag_field="calibration_type", kw_only=True):
    calibration_name: str
    calibrated_on_pioreactor_unit: str
    created_at: t.Annotated[datetime, Meta(tz=True)]
    curve_data_: list[float]
    curve_type: str  # ex: "poly"
    x: str
    y: str
    recorded_data: dict[t.Literal["x", "y"], list[X | Y]]

    def __post_init__(self):
        if len(self.recorded_data["x"]) != len(self.recorded_data["y"]):
            raise ValueError("Lists in `recorded_data` should have the same lengths")

    @property
    def calibration_type(self):
        return self.__struct_config__.tag

    def path_on_disk_for_device(self, device: str) -> Path:
        from pioreactor.calibrations import CALIBRATION_PATH

        calibration_dir = CALIBRATION_PATH / device
        out_file = calibration_dir / f"{self.calibration_name}.yaml"
        return out_file

    def save_to_disk_for_device(self, device: str) -> str:
        logger = create_logger("calibrations", experiment="$experiment")

        out_file = self.path_on_disk_for_device(device)
        device_dir = out_file.parent
        device_dir.mkdir(parents=True, exist_ok=True)

        # Serialize to YAML
        with out_file.open("wb") as f:
            f.write(yaml_encode(self))

        logger.info(f"Saved calibration {self.calibration_name} to {out_file}")
        return str(out_file)

    def set_as_active_calibration_for_device(self, device: str) -> None:
        from pioreactor.utils import local_persistent_storage

        logger = create_logger("calibrations", experiment="$experiment")

        if not self.exists_on_disk_for_device(device):
            self.save_to_disk_for_device(device)

        with local_persistent_storage("active_calibrations") as c:
            c[device] = self.calibration_name

        logger.info(f"Set {self.calibration_name} as active calibration for {device}")

    def remove_as_active_calibration_for_device(self, device: str) -> None:
        from pioreactor.utils import local_persistent_storage

        logger = create_logger("calibrations", experiment="$experiment")

        with local_persistent_storage("active_calibrations") as c:
            if c.get(device) == self.calibration_name:
                del c[device]
                logger.info(f"Removed {self.calibration_name} as active calibration for {device}")

    def exists_on_disk_for_device(self, device: str) -> bool:
        from pioreactor.calibrations import CALIBRATION_PATH

        target_file = CALIBRATION_PATH / device / f"{self.calibration_name}.yaml"

        return target_file.exists()

    def x_to_y(self, x: X) -> Y:
        """
        Predict y given x
        """
        assert self.curve_type == "poly"

        if len(self.curve_data_) == 0:
            raise exc.NoSolutionsFoundError(f"calibration {self}'s curve_data_ is empty")

        return sum([c * x**i for i, c in enumerate(reversed(self.curve_data_))])

    def y_to_x(self, y: Y, enforce_bounds=False) -> X:
        """
        predict x given y
        """
        assert self.curve_type == "poly"

        if len(self.curve_data_) == 0:
            raise exc.NoSolutionsFoundError(f"calibration {self}'s curve_data_ is empty")

        # we have to solve the polynomial roots numerically, possibly with complex roots
        from numpy import roots, zeros_like, real, imag
        from pioreactor.utils.math_helpers import closest_point_to_domain

        poly = self.curve_data_

        coef_shift = zeros_like(poly, dtype=float)
        coef_shift[-1] = y
        solve_for_poly = poly - coef_shift
        roots_ = roots(solve_for_poly).tolist()
        plausible_sols_: list[X] = sorted([real(r) for r in roots_ if (abs(imag(r)) < 1e-10)])

        if len(self.recorded_data["x"]) == 0:
            from math import inf

            min_X, max_X = -inf, inf
        else:
            min_X, max_X = min(self.recorded_data["x"]), max(self.recorded_data["x"])

        if len(plausible_sols_) == 0:
            raise exc.NoSolutionsFoundError("No solutions found")
        elif len(plausible_sols_) == 1:
            sol = plausible_sols_[0]

            if not enforce_bounds:
                return sol

            # if we are here, we let the downstream user decide how to proceed
            if min_X <= sol <= max_X:
                return sol
            elif sol < min_X:
                raise exc.SolutionBelowDomainError(f"Solution below domain [{min_X}, {max_X}]")
            else:
                raise exc.SolutionAboveDomainError(f"Solution above domain [{min_X}, {max_X}]")

        # what do we do with multiple solutions?
        closest_sol = closest_point_to_domain(plausible_sols_, (min_X, max_X))
        # closet sol can be inside or outside domain. If inside, happy path:
        if (min_X <= closest_sol <= max_X) or not enforce_bounds:
            return closest_sol

        # if we are here, we let the downstream user decide how to proceed
        elif closest_sol < min_X:
            raise exc.SolutionBelowDomainError("Solution below domain")
        else:
            raise exc.SolutionAboveDomainError("Solution below domain")

    def is_active(self, device: str) -> bool:
        from pioreactor.utils import local_persistent_storage

        with local_persistent_storage("active_calibrations") as c:
            return c.get(device) == self.calibration_name


class ODCalibration(CalibrationBase, kw_only=True, tag="od"):
    ir_led_intensity: float
    angle: t.Literal["45", "90", "135", "180"]
    pd_channel: t.Literal["1", "2"]
    y: str = "Voltage"


class OD600Calibration(ODCalibration, kw_only=True, tag="od600"):
    x: str = "OD600"


class SimplePeristalticPumpCalibration(CalibrationBase, kw_only=True, tag="simple_peristaltic_pump"):
    hz: t.Annotated[float, Meta(ge=0)]
    dc: t.Annotated[float, Meta(ge=0)]
    voltage: float
    x: str = "Duration"
    y: str = "Volume"

    def ml_to_duration(self, ml: pt.mL) -> pt.Seconds:
        return t.cast(pt.Seconds, self.y_to_x(ml))

    def duration_to_ml(self, duration: pt.Seconds) -> pt.mL:
        return t.cast(pt.mL, self.x_to_y(duration))


class SimpleStirringCalibration(CalibrationBase, kw_only=True, tag="simple_stirring"):
    pwm_hz: t.Annotated[float, Meta(ge=0)]
    voltage: float
    x: str = "DC %"
    y: str = "RPM"


AnyCalibration = t.Union[
    SimpleStirringCalibration,
    SimplePeristalticPumpCalibration,
    ODCalibration,
    OD600Calibration,
    CalibrationBase,
]


class Log(JSONPrintedStruct):
    message: str
    level: str
    task: str
    source: str
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class KalmanFilterOutput(JSONPrintedStruct):
    state: t.Annotated[list[float], Meta(max_length=3)]
    covariance_matrix: list[list[float]]
    timestamp: t.Annotated[datetime, Meta(tz=True)]


class Dataset(JSONPrintedStruct):
    dataset_name: str  # the unique key
    description: t.Optional[str]
    display_name: str
    has_experiment: bool
    has_unit: bool
    default_order_by: t.Optional[str]
    table: t.Optional[str] = None
    query: t.Optional[str] = None
    source: str = "app"
    timestamp_columns: list[str] = []
    always_partition_by_unit: bool = False
