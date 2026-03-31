# -*- coding: utf-8 -*-
import pytest
from pioreactor import bioreactor
from pioreactor import structs
from pioreactor.utils.timing import default_datetime_for_pioreactor


def test_get_bioreactor_value_uses_defaults() -> None:
    experiment = "test_get_bioreactor_value_uses_defaults"

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(14.0)
    assert bioreactor.get_bioreactor_value(experiment, "efflux_tube_volume_ml") == pytest.approx(14.0)
    assert bioreactor.get_bioreactor_value(experiment, "alt_media_fraction") == pytest.approx(0.0)


def test_set_bioreactor_value_persists() -> None:
    experiment = "test_set_bioreactor_value_persists"

    bioreactor.set_bioreactor_value(experiment, "current_volume_ml", 12.5)

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(12.5)
    assert bioreactor.get_all_bioreactor_values(experiment)["current_volume_ml"] == pytest.approx(12.5)


def test_get_bioreactor_descriptors_returns_structs() -> None:
    descriptors = bioreactor.get_bioreactor_descriptors()

    assert all(isinstance(descriptor, structs.BioreactorDescriptor) for descriptor in descriptors)
    assert [descriptor.key for descriptor in descriptors] == [
        "current_volume_ml",
        "efflux_tube_volume_ml",
        "alt_media_fraction",
    ]


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


def test_validate_bioreactor_value_rejects_current_volume_above_model_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bioreactor,
        "get_pioreactor_model",
        lambda: structs.Model(
            model_name="test_model",
            model_version="1.0",
            display_name="Test model",
            reactor_capacity_ml=20.0,
            reactor_max_fill_volume_ml=18.0,
            reactor_diameter_mm=27.0,
            max_temp_to_reduce_heating=63.0,
            max_temp_to_disable_heating=65.0,
            max_temp_to_shutdown=66.0,
            is_legacy=False,
            is_contrib=False,
        ),
    )

    with pytest.raises(ValueError):
        bioreactor.validate_bioreactor_value("current_volume_ml", 20.1)


def test_validate_bioreactor_value_allows_max_working_volume_above_max_fill_and_up_to_model_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bioreactor,
        "get_pioreactor_model",
        lambda: structs.Model(
            model_name="test_model",
            model_version="1.0",
            display_name="Test model",
            reactor_capacity_ml=20.0,
            reactor_max_fill_volume_ml=18.0,
            reactor_diameter_mm=27.0,
            max_temp_to_reduce_heating=63.0,
            max_temp_to_disable_heating=65.0,
            max_temp_to_shutdown=66.0,
            is_legacy=False,
            is_contrib=False,
        ),
    )

    assert bioreactor.validate_bioreactor_value("efflux_tube_volume_ml", 18.1) == pytest.approx(18.1)
    assert bioreactor.validate_bioreactor_value("efflux_tube_volume_ml", 20.0) == pytest.approx(20.0)


def test_validate_bioreactor_value_rejects_max_working_volume_above_model_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bioreactor,
        "get_pioreactor_model",
        lambda: structs.Model(
            model_name="test_model",
            model_version="1.0",
            display_name="Test model",
            reactor_capacity_ml=20.0,
            reactor_max_fill_volume_ml=18.0,
            reactor_diameter_mm=27.0,
            max_temp_to_reduce_heating=63.0,
            max_temp_to_disable_heating=65.0,
            max_temp_to_shutdown=66.0,
            is_legacy=False,
            is_contrib=False,
        ),
    )

    with pytest.raises(ValueError):
        bioreactor.validate_bioreactor_value("efflux_tube_volume_ml", 20.1)


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
        efflux_tube_volume_ml=14.0,
    ) == pytest.approx(14.0)


def test_calculate_updated_current_volume_accepts_add_media_events() -> None:
    dosing_event = structs.DosingEvent(
        volume_change=6.0,
        event="add_media",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    assert bioreactor.calculate_updated_current_volume(
        dosing_event,
        current_volume_ml=0.0,
        efflux_tube_volume_ml=14.0,
    ) == pytest.approx(6.0)


def test_calculate_updated_current_volume_rejects_additions_above_model_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bioreactor,
        "get_pioreactor_model",
        lambda: structs.Model(
            model_name="test_model",
            model_version="1.0",
            display_name="Test model",
            reactor_capacity_ml=20.0,
            reactor_max_fill_volume_ml=18.0,
            reactor_diameter_mm=27.0,
            max_temp_to_reduce_heating=63.0,
            max_temp_to_disable_heating=65.0,
            max_temp_to_shutdown=66.0,
            is_legacy=False,
            is_contrib=False,
        ),
    )

    dosing_event = structs.DosingEvent(
        volume_change=2.0,
        event="add_media",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    with pytest.raises(ValueError):
        bioreactor.calculate_updated_current_volume(
            dosing_event,
            current_volume_ml=19.0,
            efflux_tube_volume_ml=14.0,
        )


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
            efflux_tube_volume_ml=max_volume,
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
            efflux_tube_volume_ml=max_volume,
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
            efflux_tube_volume_ml=max_volume,
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
        efflux_tube_volume_ml=max_volume,
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
        efflux_tube_volume_ml=max_volume,
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
        efflux_tube_volume_ml=max_volume,
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
        efflux_tube_volume_ml=max_volume,
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
        efflux_tube_volume_ml=max_volume,
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


def test_calculate_updated_alt_media_fraction_rejects_invalid_fraction_on_unknown_event() -> None:
    dosing_event = structs.DosingEvent(
        volume_change=1.0,
        event="add_salty_media",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    with pytest.raises(ValueError):
        bioreactor.calculate_updated_alt_media_fraction(
            dosing_event,
            current_alt_media_fraction=1.25,
            current_volume_ml=10.0,
        )


def test_calculate_updated_alt_media_fraction_snaps_extreme_dilutions_to_zero() -> None:
    assert (
        bioreactor._calculate_alt_media_fraction_after_addition(
            current_alt_media_fraction=9.470347204675955e-37,
            media_delta=1.0,
            alt_media_delta=0.0,
            current_volume_ml=1.0,
        )
        == 0.0
    )
