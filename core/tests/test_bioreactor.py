# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest
from pioreactor import bioreactor
from pioreactor import structs
from pioreactor.pubsub import create_client
from pioreactor.pubsub import subscribe
from pioreactor.utils.timing import default_datetime_for_pioreactor


def test_get_bioreactor_value_uses_defaults() -> None:
    experiment = "test_get_bioreactor_value_uses_defaults"

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(14.0)
    assert bioreactor.get_bioreactor_value(experiment, "max_working_volume_ml") == pytest.approx(14.0)
    assert bioreactor.get_bioreactor_value(experiment, "alt_media_fraction") == pytest.approx(0.0)


def test_set_bioreactor_value_persists() -> None:
    experiment = "test_set_bioreactor_value_persists"

    bioreactor.set_bioreactor_value(experiment, "current_volume_ml", 12.5)

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(12.5)
    assert bioreactor.get_all_bioreactor_values(experiment)["current_volume_ml"] == pytest.approx(12.5)


@pytest.mark.parametrize(
    ("variable_name", "value"),
    [
        ("alt_media_fraction", 1.2),
        ("alt_media_fraction", -0.1),
        ("current_volume_ml", -1),
    ],
)
def test_validate_bioreactor_value_rejects_out_of_bounds(variable_name: str, value: float) -> None:
    with pytest.raises(ValueError):
        bioreactor.validate_bioreactor_value(variable_name, value)


def test_handle_bioreactor_set_message_persists_and_publishes() -> None:
    unit = "unit1"
    experiment = "test_handle_bioreactor_set_message_persists_and_publishes"
    topic = bioreactor.get_bioreactor_set_topic(unit, experiment, "current_volume_ml")
    message = SimpleNamespace(topic=topic, payload=b"11.75")

    with create_client() as mqtt_client:
        _, _, variable_name, parsed_value = bioreactor.handle_bioreactor_set_message(message, mqtt_client)

    assert variable_name == "current_volume_ml"
    assert parsed_value == pytest.approx(11.75)
    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(11.75)

    retained_message = subscribe(
        bioreactor.get_bioreactor_topic(unit, experiment, "current_volume_ml"),
        timeout=1.0,
    )
    assert retained_message is not None
    assert float(retained_message.payload) == pytest.approx(11.75)


def test_calculate_updated_current_volume_respects_max_working_volume_on_remove_waste() -> None:
    dosing_event = structs.DosingEvent(
        volume_change=10.0,
        event="remove_waste",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    assert (
        bioreactor.calculate_updated_current_volume(
            dosing_event,
            current_volume_ml=15.0,
            max_working_volume_ml=14.0,
        )
        == pytest.approx(14.0)
    )
