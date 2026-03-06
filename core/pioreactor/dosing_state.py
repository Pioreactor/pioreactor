# -*- coding: utf-8 -*-
from typing import Any

from msgspec import Struct
from pioreactor import whoami
from pioreactor.config import config
from pioreactor.utils import local_persistent_storage


class DosingState(Struct):
    current_volume_ml: float
    max_working_volume_ml: float
    alt_media_fraction: float
    media_throughput: float
    alt_media_throughput: float


class DosingStatePatch(Struct, omit_defaults=True):
    current_volume_ml: float | None = None
    max_working_volume_ml: float | None = None
    alt_media_fraction: float | None = None
    media_throughput: float | None = None
    alt_media_throughput: float | None = None


DOSING_STATE_FIELDS = (
    "current_volume_ml",
    "max_working_volume_ml",
    "alt_media_fraction",
    "media_throughput",
    "alt_media_throughput",
)


def _default_dosing_state() -> DosingState:
    return DosingState(
        current_volume_ml=config.getfloat("bioreactor", "initial_volume_ml", fallback=14.0),
        max_working_volume_ml=config.getfloat("bioreactor", "max_working_volume_ml", fallback=14.0),
        alt_media_fraction=config.getfloat("bioreactor", "initial_alt_media_fraction", fallback=0.0),
        media_throughput=0.0,
        alt_media_throughput=0.0,
    )


def validate_dosing_state_field(name: str, value: float) -> float:
    if name in {"current_volume_ml", "max_working_volume_ml"}:
        if value < 0:
            raise ValueError(f"{name} must be non-negative.")
        if value > whoami.get_pioreactor_model().reactor_max_fill_volume_ml:
            raise ValueError(
                f"{name} must be <= {whoami.get_pioreactor_model().reactor_max_fill_volume_ml} mL."
            )
        return value

    if name == "alt_media_fraction":
        if not 0.0 <= value <= 1.0:
            raise ValueError("alt_media_fraction must be between 0 and 1.")
        return value

    if name in {"media_throughput", "alt_media_throughput"}:
        if value < 0:
            raise ValueError(f"{name} must be non-negative.")
        return value

    raise KeyError(f"Unknown dosing state field: {name}")


def get_default_dosing_state() -> DosingState:
    defaults = _default_dosing_state()
    return DosingState(
        current_volume_ml=validate_dosing_state_field("current_volume_ml", defaults.current_volume_ml),
        max_working_volume_ml=validate_dosing_state_field(
            "max_working_volume_ml", defaults.max_working_volume_ml
        ),
        alt_media_fraction=validate_dosing_state_field("alt_media_fraction", defaults.alt_media_fraction),
        media_throughput=validate_dosing_state_field("media_throughput", defaults.media_throughput),
        alt_media_throughput=validate_dosing_state_field(
            "alt_media_throughput", defaults.alt_media_throughput
        ),
    )


def get_dosing_state(experiment: str) -> DosingState:
    defaults = get_default_dosing_state()
    state: dict[str, float] = {
        "current_volume_ml": defaults.current_volume_ml,
        "max_working_volume_ml": defaults.max_working_volume_ml,
        "alt_media_fraction": defaults.alt_media_fraction,
        "media_throughput": defaults.media_throughput,
        "alt_media_throughput": defaults.alt_media_throughput,
    }

    for field_name in DOSING_STATE_FIELDS:
        with local_persistent_storage(field_name) as cache:
            cached_value = cache.get(experiment, state[field_name])
        state[field_name] = validate_dosing_state_field(field_name, float(cached_value))

    return DosingState(**state)


def persist_dosing_state_field(experiment: str, field_name: str, value: float) -> float:
    normalized_value = validate_dosing_state_field(field_name, float(value))
    with local_persistent_storage(field_name) as cache:
        cache[experiment] = normalized_value
    return normalized_value


def persist_dosing_state(experiment: str, state: DosingState) -> DosingState:
    for field_name in DOSING_STATE_FIELDS:
        persist_dosing_state_field(experiment, field_name, getattr(state, field_name))
    return state


def apply_dosing_state_patch(experiment: str, patch: DosingStatePatch | dict[str, Any]) -> DosingState:
    current_state = get_dosing_state(experiment)

    if isinstance(patch, DosingStatePatch):
        patch_data = {
            field_name: getattr(patch, field_name)
            for field_name in DOSING_STATE_FIELDS
            if getattr(patch, field_name) is not None
        }
    else:
        patch_data = {field_name: value for field_name, value in patch.items() if value is not None}

    next_state = DosingState(
        current_volume_ml=current_state.current_volume_ml,
        max_working_volume_ml=current_state.max_working_volume_ml,
        alt_media_fraction=current_state.alt_media_fraction,
        media_throughput=current_state.media_throughput,
        alt_media_throughput=current_state.alt_media_throughput,
    )

    for field_name, value in patch_data.items():
        if field_name not in DOSING_STATE_FIELDS:
            raise KeyError(f"Unknown dosing state field: {field_name}")
        setattr(next_state, field_name, validate_dosing_state_field(field_name, float(value)))

    return persist_dosing_state(experiment, next_state)
