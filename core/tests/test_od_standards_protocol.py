# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from typing import cast
from typing import Iterator

import pytest
from pioreactor.calibrations.protocols import od_standards
from pioreactor.config import config


@contextmanager
def _temporary_config_section(section_name: str, values: dict[str, str]) -> Iterator[None]:
    created = False
    if section_name not in config:
        config.add_section(section_name)
        created = True

    section = config[section_name]
    backup = dict(section)

    section.clear()
    section.update(values)
    try:
        yield
    finally:
        section.clear()
        section.update(backup)
        if created and not backup:
            config.remove_section(section_name)


def test_channel_angle_map_from_config_requires_ref() -> None:
    with _temporary_config_section("od_config.photodiode_channel", {"1": "45"}):
        with pytest.raises(ValueError, match="REF required"):
            od_standards._channel_angle_map_from_config("od")


def test_channel_angle_map_from_config_requires_non_ref_channel() -> None:
    with _temporary_config_section("od_config.photodiode_channel", {"1": od_standards.REF_keyword}):
        with pytest.raises(ValueError, match="Need at least one non-REF"):
            od_standards._channel_angle_map_from_config("od")


def test_channel_angle_map_from_config_filters_target_device() -> None:
    with _temporary_config_section(
        "od_config.photodiode_channel",
        {"1": od_standards.REF_keyword, "2": "45", "3": "90"},
    ):
        mapping = od_standards._channel_angle_map_from_config("od90")

    assert mapping == {"3": "90"}


def test_channel_angle_map_from_config_raises_on_missing_target_angle() -> None:
    with _temporary_config_section(
        "od_config.photodiode_channel",
        {"1": od_standards.REF_keyword, "2": "45"},
    ):
        with pytest.raises(ValueError, match="No channels configured for angle 90"):
            od_standards._channel_angle_map_from_config("od90")


def test_devices_for_angles_sorted() -> None:
    devices = od_standards._devices_for_angles({"1": "135", "2": "45", "3": "90"})
    assert devices == ["od45", "od90", "od135"]


def test_build_standards_chart_metadata_handles_mismatched_lengths() -> None:
    metadata = od_standards._build_standards_chart_metadata(
        od600_values=[0.1, 0.2],
        voltages_by_channel={"1": [1.1], "2": [2.2, 2.3]},
        channel_angle_map={"1": "45", "2": "90"},
    )

    assert metadata is not None
    series = cast(list[dict[str, object]], metadata["series"])
    points0 = cast(list[dict[str, float]], series[0]["points"])
    points1 = cast(list[dict[str, float]], series[1]["points"])
    assert points0 == [{"x": 0.1, "y": 1.1}]
    assert points1 == [{"x": 0.1, "y": 2.2}, {"x": 0.2, "y": 2.3}]
