# -*- coding: utf-8 -*-
from contextlib import AbstractContextManager

import pytest
from pioreactor import bioreactor
from pioreactor import structs
from pioreactor.pubsub import QOS
from pioreactor.utils import sqlite_cache
from pioreactor.utils.timing import default_datetime_for_pioreactor
from tests.utils import FakeMQTTClient
from tests.utils import FakeMQTTMessageInfo


def test_get_bioreactor_value_uses_defaults() -> None:
    experiment = "test_get_bioreactor_value_uses_defaults"

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(14.0)
    assert bioreactor.get_bioreactor_value(experiment, "efflux_tube_volume_ml") == pytest.approx(14.0)
    assert bioreactor.get_bioreactor_value(experiment, "alt_media_fraction") == pytest.approx(0.0)
    assert bioreactor.get_bioreactor_value(experiment, "cumulative_media_added_ml") == pytest.approx(0.0)
    assert bioreactor.get_bioreactor_value(experiment, "cumulative_alt_media_added_ml") == pytest.approx(0.0)
    assert bioreactor.get_bioreactor_value(experiment, "cumulative_waste_removed_ml") == pytest.approx(0.0)


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


def test_validate_bioreactor_value_allows_cumulative_volume_above_model_capacity(
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

    assert bioreactor.validate_bioreactor_value("cumulative_media_added_ml", 80.0) == pytest.approx(80.0)


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


def test_calculate_updated_current_volume_does_not_go_below_efflux_level_on_remove_waste() -> None:
    dosing_event = structs.DosingEvent(
        volume_change=10.0,
        event="remove_waste",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    assert bioreactor.calculate_updated_current_volume(
        dosing_event,
        current_volume_ml=3.0,
        efflux_tube_volume_ml=3.0,
    ) == pytest.approx(3.0)


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


def test_calculate_updated_cumulative_volume_tracks_matching_events() -> None:
    event = structs.DosingEvent(
        volume_change=1.25,
        event="add_media",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    assert bioreactor.calculate_updated_cumulative_volume(
        "cumulative_media_added_ml",
        event,
        current_cumulative_volume_ml=2.0,
    ) == pytest.approx(3.25)
    assert bioreactor.calculate_updated_cumulative_volume(
        "cumulative_alt_media_added_ml",
        event,
        current_cumulative_volume_ml=2.0,
    ) == pytest.approx(2.0)


def test_calculate_updated_cumulative_volume_does_not_go_negative() -> None:
    event = structs.DosingEvent(
        volume_change=-2.0,
        event="remove_waste",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    assert bioreactor.calculate_updated_cumulative_volume(
        "cumulative_waste_removed_ml",
        event,
        current_cumulative_volume_ml=1.0,
    ) == pytest.approx(0.0)


def test_apply_dosing_event_to_bioreactor_persists_cumulative_volumes() -> None:
    experiment = "test_apply_dosing_event_to_bioreactor_persists_cumulative_volumes"
    mqtt_client = FakeMQTTClient()

    add_media_event = structs.DosingEvent(
        volume_change=1.25,
        event="add_media",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )
    add_alt_media_event = structs.DosingEvent(
        volume_change=0.5,
        event="add_alt_media",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )
    remove_waste_event = structs.DosingEvent(
        volume_change=0.75,
        event="remove_waste",
        source_of_event="test",
        timestamp=default_datetime_for_pioreactor(),
    )

    bioreactor.apply_dosing_event_to_bioreactor("unit", experiment, add_media_event, mqtt_client)
    bioreactor.apply_dosing_event_to_bioreactor("unit", experiment, add_alt_media_event, mqtt_client)
    updated = bioreactor.apply_dosing_event_to_bioreactor(
        "unit",
        experiment,
        remove_waste_event,
        mqtt_client,
    )

    assert updated["cumulative_media_added_ml"] == pytest.approx(1.25)
    assert updated["cumulative_alt_media_added_ml"] == pytest.approx(0.5)
    assert updated["cumulative_waste_removed_ml"] == pytest.approx(0.75)
    assert bioreactor.get_bioreactor_value(experiment, "cumulative_media_added_ml") == pytest.approx(1.25)
    assert bioreactor.get_bioreactor_value(experiment, "cumulative_alt_media_added_ml") == pytest.approx(0.5)
    assert bioreactor.get_bioreactor_value(experiment, "cumulative_waste_removed_ml") == pytest.approx(0.75)
    assert (
        bioreactor.get_bioreactor_topic("unit", experiment, "cumulative_waste_removed_ml"),
        0.75,
        True,
    ) in mqtt_client.published


def test_apply_dosing_event_uses_one_storage_context_and_enqueues_all_publications_before_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment = "test_apply_dosing_event_uses_one_storage_context"
    bioreactor.set_bioreactor_value(experiment, "current_volume_ml", 10.0)
    bioreactor.set_bioreactor_value(experiment, "efflux_tube_volume_ml", 8.0)
    bioreactor.set_bioreactor_value(experiment, "alt_media_fraction", 0.25)
    bioreactor.set_bioreactor_value(experiment, "cumulative_media_added_ml", 3.0)
    bioreactor.set_bioreactor_value(experiment, "cumulative_alt_media_added_ml", 4.0)
    bioreactor.set_bioreactor_value(experiment, "cumulative_waste_removed_ml", 5.0)

    storage_context_count = 0
    local_persistent_storage = bioreactor.local_persistent_storage

    def counted_local_persistent_storage(
        cache_name: str,
    ) -> AbstractContextManager[sqlite_cache.cache]:
        nonlocal storage_context_count
        storage_context_count += 1
        return local_persistent_storage(cache_name)

    monkeypatch.setattr(bioreactor, "local_persistent_storage", counted_local_persistent_storage)

    operations: list[str] = []
    mqtt_client: FakeMQTTClient

    def record_publish(_topic: str, _payload: object, **_kwargs: object) -> None:
        operations.append("publish")

    def record_wait(_timeout: float | None) -> None:
        operations.append("wait")
        assert len(mqtt_client.publish_calls) == 5

    mqtt_client = FakeMQTTClient(
        on_publish=record_publish,
        message_info_factory=lambda: FakeMQTTMessageInfo(on_wait=record_wait),
    )
    monotonic_values = iter((100.0, 101.0, 103.0, 106.0, 110.0, 111.0))
    monkeypatch.setattr(bioreactor, "monotonic", lambda: next(monotonic_values), raising=False)

    updated = bioreactor.apply_dosing_event_to_bioreactor(
        "unit",
        experiment,
        structs.DosingEvent(
            volume_change=2.0,
            event="add_media",
            source_of_event="test",
            timestamp=default_datetime_for_pioreactor(),
        ),
        mqtt_client,
    )

    assert storage_context_count == 1
    assert updated == pytest.approx(
        {
            "alt_media_fraction": 2.5 / 12.0,
            "current_volume_ml": 12.0,
            "cumulative_media_added_ml": 5.0,
            "cumulative_alt_media_added_ml": 4.0,
            "cumulative_waste_removed_ml": 5.0,
        }
    )
    assert operations == ["publish"] * 5 + ["wait"] * 5
    assert [call["topic"].rsplit("/", 1)[-1] for call in mqtt_client.publish_calls] == [
        "alt_media_fraction",
        "current_volume_ml",
        "cumulative_media_added_ml",
        "cumulative_alt_media_added_ml",
        "cumulative_waste_removed_ml",
    ]
    assert all(call["retain"] is True for call in mqtt_client.publish_calls)
    assert all(call["kwargs"] == {"qos": QOS.EXACTLY_ONCE} for call in mqtt_client.publish_calls)
    assert [message_info.wait_calls for message_info in mqtt_client.message_infos] == [
        [9.0],
        [7.0],
        [4.0],
        [0.0],
        [0.0],
    ]


def test_apply_dosing_event_rolls_back_all_storage_updates_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment = "test_apply_dosing_event_rolls_back_all_storage_updates_on_failure"
    bioreactor.set_bioreactor_value(experiment, "current_volume_ml", 10.0)
    bioreactor.set_bioreactor_value(experiment, "cumulative_media_added_ml", 3.0)

    setitem_count = 0
    setitem = sqlite_cache.cache.__setitem__

    def fail_after_second_setitem(cache: sqlite_cache.cache, key: object, value: object) -> None:
        nonlocal setitem_count
        setitem(cache, key, value)
        setitem_count += 1
        if setitem_count == 2:
            raise RuntimeError("storage failed")

    monkeypatch.setattr(sqlite_cache.cache, "__setitem__", fail_after_second_setitem)
    mqtt_client = FakeMQTTClient()

    with pytest.raises(RuntimeError, match="storage failed"):
        bioreactor.apply_dosing_event_to_bioreactor(
            "unit",
            experiment,
            structs.DosingEvent(
                volume_change=2.0,
                event="add_media",
                source_of_event="test",
                timestamp=default_datetime_for_pioreactor(),
            ),
            mqtt_client,
        )

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(10.0)
    assert bioreactor.get_bioreactor_value(experiment, "cumulative_media_added_ml") == pytest.approx(3.0)
    assert mqtt_client.publish_calls == []


def test_apply_dosing_event_reports_unacknowledged_publications_after_persisting_state() -> None:
    experiment = "test_apply_dosing_event_reports_unacknowledged_publications"
    bioreactor.set_bioreactor_value(experiment, "current_volume_ml", 10.0)
    published_results = iter((True, False, True, True, True))
    mqtt_client = FakeMQTTClient(
        message_info_factory=lambda: FakeMQTTMessageInfo(published=next(published_results))
    )

    with pytest.raises(RuntimeError, match="current_volume_ml"):
        bioreactor.apply_dosing_event_to_bioreactor(
            "unit",
            experiment,
            structs.DosingEvent(
                volume_change=2.0,
                event="add_media",
                source_of_event="test",
                timestamp=default_datetime_for_pioreactor(),
            ),
            mqtt_client,
        )

    assert bioreactor.get_bioreactor_value(experiment, "current_volume_ml") == pytest.approx(12.0)
    assert len(mqtt_client.publish_calls) == 5
    assert all(len(message_info.wait_calls) == 1 for message_info in mqtt_client.message_infos)


@pytest.mark.parametrize(
    ("event", "volume_change", "expected"),
    [
        ("add_media", 0.0, (10.0, 0.25, 3.0, 4.0, 5.0)),
        ("add_media", -2.0, (8.0, 0.3125, 1.0, 4.0, 5.0)),
        ("add_alt_media", -2.0, (8.0, 0.0625, 3.0, 2.0, 5.0)),
        ("remove_waste", -2.0, (12.0, 0.25, 3.0, 4.0, 3.0)),
    ],
)
def test_apply_dosing_event_preserves_zero_and_negative_corrections(
    event: str,
    volume_change: float,
    expected: tuple[float, float, float, float, float],
) -> None:
    experiment = f"test_apply_dosing_event_preserves_corrections_{event}_{volume_change}"
    bioreactor.set_bioreactor_value(experiment, "current_volume_ml", 10.0)
    bioreactor.set_bioreactor_value(experiment, "efflux_tube_volume_ml", 8.0)
    bioreactor.set_bioreactor_value(experiment, "alt_media_fraction", 0.25)
    bioreactor.set_bioreactor_value(experiment, "cumulative_media_added_ml", 3.0)
    bioreactor.set_bioreactor_value(experiment, "cumulative_alt_media_added_ml", 4.0)
    bioreactor.set_bioreactor_value(experiment, "cumulative_waste_removed_ml", 5.0)

    updated = bioreactor.apply_dosing_event_to_bioreactor(
        "unit",
        experiment,
        structs.DosingEvent(
            volume_change=volume_change,
            event=event,
            source_of_event="test",
            timestamp=default_datetime_for_pioreactor(),
        ),
        FakeMQTTClient(),
    )

    assert updated == pytest.approx(
        {
            "current_volume_ml": expected[0],
            "alt_media_fraction": expected[1],
            "cumulative_media_added_ml": expected[2],
            "cumulative_alt_media_added_ml": expected[3],
            "cumulative_waste_removed_ml": expected[4],
        }
    )


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
