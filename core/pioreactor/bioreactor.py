# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import typing as t

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.config import config
from pioreactor.pubsub import publish as mqtt_publish
from pioreactor.pubsub import QOS
from pioreactor.utils import local_persistent_storage

BIOREACTOR_STORAGE_NAME = "bioreactor"


type _BioreactorDefaultResolver = t.Callable[[], float]
type BioreactorDescriptor = dict[str, str | float | None]


_BIOREACTOR_VARIABLES: dict[str, dict[str, str | float | None | _BioreactorDefaultResolver]] = {
    "current_volume_ml": {
        "label": "Current volume",
        "description": "Current estimated liquid volume in the vial.",
        "unit": "mL",
        "min": 0.0,
        "max": None,
        "default_resolver": lambda: config.getfloat("bioreactor", "initial_volume_ml", fallback=14.0),
    },
    "max_working_volume_ml": {
        "label": "Max working volume",
        "description": "Target overflow height for normal waste removal calculations.",
        "unit": "mL",
        "min": 0.0,
        "max": None,
        "default_resolver": lambda: config.getfloat("bioreactor", "max_working_volume_ml", fallback=14.0),
    },
    "alt_media_fraction": {
        "label": "Alt media fraction",
        "description": "Fraction of the vial estimated to contain alt media.",
        "unit": None,
        "min": 0.0,
        "max": 1.0,
        "default_resolver": lambda: config.getfloat(
            "bioreactor",
            "initial_alt_media_fraction",
            fallback=0.0,
        ),
    },
}


def get_bioreactor_variable_names() -> tuple[str, ...]:
    return tuple(_BIOREACTOR_VARIABLES.keys())


def get_default_bioreactor_value(variable_name: str) -> float:
    metadata = _get_bioreactor_metadata(variable_name)
    resolver = t.cast(_BioreactorDefaultResolver, metadata["default_resolver"])
    return validate_bioreactor_value(variable_name, resolver())


def get_bioreactor_descriptors() -> list[BioreactorDescriptor]:
    descriptors: list[BioreactorDescriptor] = []

    for variable_name, metadata in _BIOREACTOR_VARIABLES.items():
        descriptors.append(
            {
                "key": variable_name,
                "label": t.cast(str, metadata["label"]),
                "description": t.cast(str, metadata["description"]),
                "type": "numeric",
                "unit": t.cast(str | None, metadata["unit"]),
                "min": t.cast(float | None, metadata["min"]),
                "max": t.cast(float | None, metadata["max"]),
                "default": get_default_bioreactor_value(variable_name),
            }
        )

    return descriptors


def validate_bioreactor_value(variable_name: str, value: object) -> float:
    metadata = _get_bioreactor_metadata(variable_name)

    try:
        parsed = _coerce_to_float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid value for bioreactor variable `{variable_name}`.") from e

    if not math.isfinite(parsed):
        raise ValueError(f"Value for bioreactor variable `{variable_name}` must be finite.")

    minimum = t.cast(float | None, metadata["min"])
    maximum = t.cast(float | None, metadata["max"])

    if (minimum is not None) and (parsed < minimum):
        raise ValueError(f"Value for bioreactor variable `{variable_name}` must be >= {minimum}.")

    if (maximum is not None) and (parsed > maximum):
        raise ValueError(f"Value for bioreactor variable `{variable_name}` must be <= {maximum}.")

    return parsed


def get_bioreactor_value(experiment: pt.Experiment, variable_name: str) -> float:
    _get_bioreactor_metadata(variable_name)

    with local_persistent_storage(BIOREACTOR_STORAGE_NAME) as cache:
        stored_value = cache.get((experiment, variable_name))

    if stored_value is None:
        return get_default_bioreactor_value(variable_name)

    return validate_bioreactor_value(variable_name, stored_value)


def get_all_bioreactor_values(experiment: pt.Experiment) -> dict[str, float]:
    return {
        variable_name: get_bioreactor_value(experiment, variable_name)
        for variable_name in get_bioreactor_variable_names()
    }


def set_bioreactor_value(experiment: pt.Experiment, variable_name: str, value: object) -> float:
    parsed_value = validate_bioreactor_value(variable_name, value)

    with local_persistent_storage(BIOREACTOR_STORAGE_NAME) as cache:
        cache[(experiment, variable_name)] = parsed_value

    return parsed_value


def get_bioreactor_topic(unit: pt.Unit, experiment: pt.Experiment, variable_name: str) -> str:
    _get_bioreactor_metadata(variable_name)
    return f"pioreactor/{unit}/{experiment}/bioreactor/{variable_name}"


def get_bioreactor_set_topic(unit: pt.Unit, experiment: pt.Experiment, variable_name: str) -> str:
    return get_bioreactor_topic(unit, experiment, variable_name) + "/set"


def parse_bioreactor_topic(topic: str) -> tuple[str, str, str, bool]:
    pieces = topic.split("/")
    if len(pieces) not in (5, 6):
        raise ValueError(f"Invalid bioreactor topic: {topic}")

    if pieces[0] != "pioreactor" or pieces[3] != "bioreactor":
        raise ValueError(f"Invalid bioreactor topic: {topic}")

    unit = pieces[1]
    experiment = pieces[2]
    variable_name = pieces[4]
    is_set_topic = len(pieces) == 6 and pieces[5] == "set"

    if len(pieces) == 6 and not is_set_topic:
        raise ValueError(f"Invalid bioreactor topic: {topic}")

    _get_bioreactor_metadata(variable_name)
    return unit, experiment, variable_name, is_set_topic


def publish_bioreactor_value(
    mqtt_client: "pt.Client",
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
    mqtt_client: "pt.Client",
    unit: pt.Unit,
    experiment: pt.Experiment,
    variable_name: str,
    value: object,
) -> float:
    parsed_value = set_bioreactor_value(experiment, variable_name, value)
    publish_bioreactor_value(mqtt_client, unit, experiment, variable_name, parsed_value)
    return parsed_value


def handle_bioreactor_set_message(
    message: pt.MQTTMessage, mqtt_client: "pt.Client"
) -> tuple[str, str, str, float]:
    unit, experiment, variable_name, is_set_topic = parse_bioreactor_topic(message.topic)
    if not is_set_topic:
        raise ValueError(f"Expected a bioreactor set topic, got {message.topic}")

    parsed_value = set_and_publish_bioreactor_value(
        mqtt_client,
        unit,
        experiment,
        variable_name,
        message.payload,
    )
    return unit, experiment, variable_name, parsed_value


def calculate_updated_current_volume(
    dosing_event: structs.DosingEvent,
    current_volume_ml: float,
    max_working_volume_ml: float,
) -> float:
    volume, event = float(dosing_event.volume_change), dosing_event.event

    if event in ("add_media", "add_alt_media"):
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

    raise ValueError(f"Unknown dosing event type `{event}`.")


def apply_dosing_event_to_bioreactor(
    unit: pt.Unit,
    experiment: pt.Experiment,
    dosing_event: structs.DosingEvent,
    mqtt_client: pt.Client | None = None,
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


def _get_bioreactor_metadata(
    variable_name: str,
) -> dict[str, str | float | None | _BioreactorDefaultResolver]:
    try:
        return _BIOREACTOR_VARIABLES[variable_name]
    except KeyError as e:
        raise KeyError(f"Unknown bioreactor variable `{variable_name}`.") from e


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
    return min(max(updated, 0.0), 1.0)


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
    mqtt_client: pt.Client | None = None,
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
