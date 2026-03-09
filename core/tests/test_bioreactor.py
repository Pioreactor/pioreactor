# -*- coding: utf-8 -*-
import pytest
from pioreactor import bioreactor
from pioreactor import structs
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


def test_calculate_updated_current_volume_respects_max_working_volume_on_remove_waste() -> None:
    dosing_event = structs.DosingEvent(
        volume_change=10.0,
        event="remove_waste",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    assert bioreactor.calculate_updated_current_volume(
        dosing_event,
        current_volume_ml=15.0,
        max_working_volume_ml=14.0,
    ) == pytest.approx(14.0)


def test_calculate_updated_current_volume_sequence() -> None:
    current_volume = 0.0
    max_volume = 14.0

    events = [
        structs.DosingEvent(6, "add_media", "test", default_datetime_for_pioreactor(0)),
        structs.DosingEvent(2, "remove_waste", "test", default_datetime_for_pioreactor(1)),
        structs.DosingEvent(6, "add_alt_media", "test", default_datetime_for_pioreactor(2)),
        structs.DosingEvent(3, "add_alt_media", "test", default_datetime_for_pioreactor(3)),
        structs.DosingEvent(3, "remove_waste", "test", default_datetime_for_pioreactor(4)),
        structs.DosingEvent(2, "add_alt_media", "test", default_datetime_for_pioreactor(5)),
        structs.DosingEvent(1, "remove_waste", "test", default_datetime_for_pioreactor(6)),
        structs.DosingEvent(10, "remove_waste", "test", default_datetime_for_pioreactor(7)),
    ]

    expected = [6.0, 6.0, 12.0, 15.0, 14.0, 16.0, 15.0, 14.0]

    for dosing_event, target in zip(events, expected):
        current_volume = bioreactor.calculate_updated_current_volume(
            dosing_event,
            current_volume_ml=current_volume,
            max_working_volume_ml=max_volume,
        )
        assert current_volume == pytest.approx(target)


def test_calculate_updated_current_volume_with_negative_add_media_values() -> None:
    current_volume = 0.0
    max_volume = 14.0

    events = [
        structs.DosingEvent(6, "add_media", "test", default_datetime_for_pioreactor(0)),
        structs.DosingEvent(-3, "add_media", "test", default_datetime_for_pioreactor(1)),
        structs.DosingEvent(-3, "add_media", "test", default_datetime_for_pioreactor(2)),
        structs.DosingEvent(-3, "add_media", "test", default_datetime_for_pioreactor(3)),
    ]
    expected = [6.0, 3.0, 0.0, 0.0]

    for dosing_event, target in zip(events, expected):
        current_volume = bioreactor.calculate_updated_current_volume(
            dosing_event,
            current_volume_ml=current_volume,
            max_working_volume_ml=max_volume,
        )
        assert current_volume == pytest.approx(target)


def test_calculate_updated_alt_media_fraction_sequence() -> None:
    current_volume = 0.0
    max_volume = 14.0
    current_alt_media_fraction = 0.0

    events = [
        structs.DosingEvent(6, "add_media", "test", default_datetime_for_pioreactor(0)),
        structs.DosingEvent(2, "remove_waste", "test", default_datetime_for_pioreactor(1)),
        structs.DosingEvent(6, "add_alt_media", "test", default_datetime_for_pioreactor(2)),
        structs.DosingEvent(3, "add_alt_media", "test", default_datetime_for_pioreactor(3)),
    ]
    expected = [0.0, 0.0, 0.5, 0.6]

    for dosing_event, target in zip(events, expected):
        current_alt_media_fraction = bioreactor.calculate_updated_alt_media_fraction(
            dosing_event,
            current_alt_media_fraction=current_alt_media_fraction,
            current_volume_ml=current_volume,
        )
        current_volume = bioreactor.calculate_updated_current_volume(
            dosing_event,
            current_volume_ml=current_volume,
            max_working_volume_ml=max_volume,
        )
        assert current_alt_media_fraction == pytest.approx(target)


def test_calculate_updated_alt_media_fraction_with_negative_alt_media_dose() -> None:
    current_volume = 0.0
    max_volume = 14.0
    current_alt_media_fraction = 0.0

    event = structs.DosingEvent(6, "add_media", "test", default_datetime_for_pioreactor(0))
    current_alt_media_fraction = bioreactor.calculate_updated_alt_media_fraction(
        event,
        current_alt_media_fraction=current_alt_media_fraction,
        current_volume_ml=current_volume,
    )
    current_volume = bioreactor.calculate_updated_current_volume(
        event,
        current_volume_ml=current_volume,
        max_working_volume_ml=max_volume,
    )

    event = structs.DosingEvent(6, "add_alt_media", "test", default_datetime_for_pioreactor(1))
    current_alt_media_fraction = bioreactor.calculate_updated_alt_media_fraction(
        event,
        current_alt_media_fraction=current_alt_media_fraction,
        current_volume_ml=current_volume,
    )
    current_volume = bioreactor.calculate_updated_current_volume(
        event,
        current_volume_ml=current_volume,
        max_working_volume_ml=max_volume,
    )

    event = structs.DosingEvent(6, "add_alt_media", "test", default_datetime_for_pioreactor(2))
    branch_a_fraction = bioreactor.calculate_updated_alt_media_fraction(
        event,
        current_alt_media_fraction=current_alt_media_fraction,
        current_volume_ml=current_volume,
    )
    branch_a_volume = bioreactor.calculate_updated_current_volume(
        event,
        current_volume_ml=current_volume,
        max_working_volume_ml=max_volume,
    )

    correction_event = structs.DosingEvent(-3, "add_alt_media", "test", default_datetime_for_pioreactor(3))
    corrected_fraction = bioreactor.calculate_updated_alt_media_fraction(
        correction_event,
        current_alt_media_fraction=branch_a_fraction,
        current_volume_ml=branch_a_volume,
    )
    corrected_volume = bioreactor.calculate_updated_current_volume(
        correction_event,
        current_volume_ml=branch_a_volume,
        max_working_volume_ml=max_volume,
    )

    direct_event = structs.DosingEvent(3, "add_alt_media", "test", default_datetime_for_pioreactor(2))
    direct_fraction = bioreactor.calculate_updated_alt_media_fraction(
        direct_event,
        current_alt_media_fraction=current_alt_media_fraction,
        current_volume_ml=current_volume,
    )
    direct_volume = bioreactor.calculate_updated_current_volume(
        direct_event,
        current_volume_ml=current_volume,
        max_working_volume_ml=max_volume,
    )

    assert corrected_fraction == pytest.approx(direct_fraction)
    assert corrected_volume == pytest.approx(direct_volume)


def test_calculate_updated_alt_media_fraction_ignores_unknown_events() -> None:
    dosing_event = structs.DosingEvent(
        volume_change=1.0,
        event="add_salty_media",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    assert bioreactor.calculate_updated_alt_media_fraction(
        dosing_event,
        current_alt_media_fraction=0.25,
        current_volume_ml=10.0,
    ) == pytest.approx(0.25)
