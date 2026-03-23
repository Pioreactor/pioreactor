# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.config import config
from pioreactor.pubsub import Client
from pioreactor.pubsub import publish as mqtt_publish
from pioreactor.pubsub import QOS
from pioreactor.utils import clamp
from pioreactor.utils import local_persistent_storage
from pioreactor.whoami import get_pioreactor_model


_BIOREACTOR_VARIABLES: dict[str, structs.BioreactorVariableDefinition] = {
    "current_volume_ml": structs.BioreactorVariableDefinition(
        key="current_volume_ml",
        label="Current volume",
        description="Current estimated liquid volume in the vial.",
        unit="mL",
        minimum=0.0,
        maximum=None,
        default_config_key="initial_volume_ml",
        default_value=14.0,
    ),
    "max_working_volume_ml": structs.BioreactorVariableDefinition(
        key="max_working_volume_ml",
        label="Max working volume",
        description="Target overflow height for normal waste removal calculations.",
        unit="mL",
        minimum=0.0,
        maximum=None,
        default_config_key="max_working_volume_ml",
        default_value=14.0,
    ),
    "alt_media_fraction": structs.BioreactorVariableDefinition(
        key="alt_media_fraction",
        label="Alt media fraction",
        description="Fraction of the vial estimated to contain alt media.",
        unit=None,
        minimum=0.0,
        maximum=1.0,
        default_config_key="initial_alt_media_fraction",
        default_value=0.0,
    ),
}


def _get_bioreactor_variable_definition(variable_name: str) -> structs.BioreactorVariableDefinition:
    return _BIOREACTOR_VARIABLES[variable_name]


def get_default_bioreactor_value(variable_name: str) -> float:
    metadata = _get_bioreactor_variable_definition(variable_name)
    resolved_default = config.getfloat(
        "bioreactor",
        metadata.default_config_key,
        fallback=metadata.default_value,
    )
    return validate_bioreactor_value(variable_name, resolved_default)


def get_bioreactor_descriptors() -> list[structs.BioreactorDescriptor]:
    descriptors: list[structs.BioreactorDescriptor] = []

    for metadata in _BIOREACTOR_VARIABLES.values():
        descriptors.append(
            structs.BioreactorDescriptor(
                key=metadata.key,
                label=metadata.label,
                description=metadata.description,
                type="numeric",
                unit=metadata.unit,
                min=metadata.minimum,
                max=metadata.maximum,
            )
        )

    return descriptors


def validate_bioreactor_value(variable_name: str, value: object) -> float:
    metadata = _get_bioreactor_variable_definition(variable_name)

    try:
        parsed = _coerce_to_float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid value for bioreactor variable `{variable_name}`.") from e

    minimum = metadata.minimum
    maximum = get_pioreactor_model().reactor_max_fill_volume_ml

    if metadata.maximum is not None:
        maximum = min(maximum, metadata.maximum)

    if parsed < minimum:
        raise ValueError(f"Value for bioreactor variable `{variable_name}` must be >= {minimum}.")

    if parsed > maximum:
        raise ValueError(f"Value for bioreactor variable `{variable_name}` must be <= {maximum}.")

    return parsed


def get_bioreactor_value(experiment: pt.Experiment, variable_name: str) -> float:

    with local_persistent_storage("bioreactor") as cache:
        stored_value = cache.get((experiment, variable_name))

    if stored_value is None:
        return get_default_bioreactor_value(variable_name)

    return validate_bioreactor_value(variable_name, stored_value)


def get_all_bioreactor_values(experiment: pt.Experiment) -> dict[str, float]:
    return {
        variable_name: get_bioreactor_value(experiment, variable_name)
        for variable_name in _BIOREACTOR_VARIABLES
    }


def set_bioreactor_value(experiment: pt.Experiment, variable_name: str, value: object) -> float:
    parsed_value = validate_bioreactor_value(variable_name, value)

    with local_persistent_storage("bioreactor") as cache:
        cache[(experiment, variable_name)] = parsed_value

    return parsed_value


def get_bioreactor_topic(unit: pt.Unit, experiment: pt.Experiment, variable_name: str) -> str:
    return f"pioreactor/{unit}/{experiment}/bioreactor/{variable_name}"


def publish_bioreactor_value(
    mqtt_client: Client,
    unit: pt.Unit,
    experiment: pt.Experiment,
    variable_name: str,
    value: object,
) -> float:
    parsed_value = validate_bioreactor_value(variable_name, value)
    msg_info = mqtt_client.publish(
        get_bioreactor_topic(unit, experiment, variable_name),
        parsed_value,
        qos=QOS.EXACTLY_ONCE,
        retain=True,
    )
    msg_info.wait_for_publish(timeout=10)
    return parsed_value


def set_and_publish_bioreactor_value(
    mqtt_client: Client,
    unit: pt.Unit,
    experiment: pt.Experiment,
    variable_name: str,
    value: object,
) -> float:
    parsed_value = set_bioreactor_value(experiment, variable_name, value)
    publish_bioreactor_value(mqtt_client, unit, experiment, variable_name, parsed_value)
    return parsed_value


def calculate_updated_current_volume(
    dosing_event: structs.DosingEvent,
    current_volume_ml: float,
    max_working_volume_ml: float,
) -> float:
    volume, event = float(dosing_event.volume_change), dosing_event.event

    if event == "add_alt_media" or event.startswith("add_"):
        return max(current_volume_ml + volume, 0.0)

    if event == "remove_waste":
        if current_volume_ml <= max_working_volume_ml:
            return max(current_volume_ml, 0.0)
        return max(current_volume_ml - volume, max_working_volume_ml, 0.0)

    raise ValueError(f"Unknown dosing event type `{event}`.")


def calculate_updated_alt_media_fraction(
    dosing_event: structs.DosingEvent,
    current_alt_media_fraction: float,
    current_volume_ml: float,
) -> float:
    volume, event = float(dosing_event.volume_change), dosing_event.event

    if event == "add_media":
        return _calculate_alt_media_fraction_after_addition(
            current_alt_media_fraction,
            media_delta=volume,
            alt_media_delta=0.0,
            current_volume_ml=current_volume_ml,
        )

    if event == "add_alt_media":
        return _calculate_alt_media_fraction_after_addition(
            current_alt_media_fraction,
            media_delta=0.0,
            alt_media_delta=volume,
            current_volume_ml=current_volume_ml,
        )

    if event == "remove_waste":
        return current_alt_media_fraction

    return current_alt_media_fraction


def apply_dosing_event_to_bioreactor(
    unit: pt.Unit,
    experiment: pt.Experiment,
    dosing_event: structs.DosingEvent,
    mqtt_client: Client | None = None,
) -> dict[str, float]:
    current_volume_ml = get_bioreactor_value(experiment, "current_volume_ml")
    max_working_volume_ml = get_bioreactor_value(experiment, "max_working_volume_ml")
    current_alt_media_fraction = get_bioreactor_value(experiment, "alt_media_fraction")

    updated_alt_media_fraction = calculate_updated_alt_media_fraction(
        dosing_event,
        current_alt_media_fraction=current_alt_media_fraction,
        current_volume_ml=current_volume_ml,
    )
    updated_current_volume_ml = calculate_updated_current_volume(
        dosing_event,
        current_volume_ml=current_volume_ml,
        max_working_volume_ml=max_working_volume_ml,
    )

    updated_alt_media_fraction = set_bioreactor_value(
        experiment,
        "alt_media_fraction",
        updated_alt_media_fraction,
    )
    updated_current_volume_ml = set_bioreactor_value(
        experiment,
        "current_volume_ml",
        updated_current_volume_ml,
    )

    _publish_updated_bioreactor_value(
        unit,
        experiment,
        "alt_media_fraction",
        updated_alt_media_fraction,
        mqtt_client=mqtt_client,
    )
    _publish_updated_bioreactor_value(
        unit,
        experiment,
        "current_volume_ml",
        updated_current_volume_ml,
        mqtt_client=mqtt_client,
    )

    return {
        "alt_media_fraction": updated_alt_media_fraction,
        "current_volume_ml": updated_current_volume_ml,
    }


def _calculate_alt_media_fraction_after_addition(
    current_alt_media_fraction: float,
    media_delta: float,
    alt_media_delta: float,
    current_volume_ml: float,
) -> float:
    total_addition = media_delta + alt_media_delta
    denominator = current_volume_ml + total_addition
    if denominator <= 0:
        return current_alt_media_fraction

    updated = (current_alt_media_fraction * current_volume_ml + alt_media_delta) / denominator

    tol = 1e-12

    if abs(updated) < tol:
        return 0.0
    if abs(1.0 - updated) < tol:
        return 1.0
    return clamp(0.0, updated, 1.0)


def _coerce_to_float(value: object) -> float:
    if isinstance(value, bytes):
        return float(value.decode("utf-8"))

    if isinstance(value, bytearray):
        return float(bytes(value).decode("utf-8"))

    if isinstance(value, memoryview):
        return float(value.tobytes().decode("utf-8"))

    if isinstance(value, str | int | float):
        return float(value)

    return float(t.cast(t.SupportsFloat, value))


def _publish_updated_bioreactor_value(
    unit: pt.Unit,
    experiment: pt.Experiment,
    variable_name: str,
    value: float,
    mqtt_client: Client | None = None,
) -> None:
    if mqtt_client is not None:
        publish_bioreactor_value(mqtt_client, unit, experiment, variable_name, value)
        return

    mqtt_publish(
        get_bioreactor_topic(unit, experiment, variable_name),
        value,
        qos=QOS.EXACTLY_ONCE,
        retain=True,
    )
