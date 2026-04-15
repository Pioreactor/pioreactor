# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from types import SimpleNamespace
from typing import Iterator

import pytest
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.calibrations.protocols import od_fusion_standards
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionInputs
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.utils.od_fusion import FUSION_ANGLES


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


def test_channel_angle_map_from_config_requires_all_angles() -> None:
    with _temporary_config_section("od_config.photodiode_channel", {"1": "45", "2": "90"}):
        with pytest.raises(ValueError, match="Fusion calibration requires PD channels configured"):
            od_fusion_standards._channel_angle_map_from_config()


def test_channel_angle_map_from_config_returns_expected_mapping() -> None:
    with _temporary_config_section("od_config.photodiode_channel", {"1": "45", "2": "90", "3": "135"}):
        mapping = od_fusion_standards._channel_angle_map_from_config()

    assert mapping == {"1": "45", "2": "90", "3": "135"}


def test_aggregate_angles_averages_by_angle() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    readings = structs.ODReadings(
        timestamp=timestamp,
        ods={
            "1": structs.RawODReading(
                timestamp=timestamp,
                angle="45",
                od=1.0,
                channel="1",
                ir_led_intensity=1.0,
            ),
            "2": structs.RawODReading(
                timestamp=timestamp,
                angle="45",
                od=3.0,
                channel="2",
                ir_led_intensity=1.0,
            ),
            "3": structs.RawODReading(
                timestamp=timestamp,
                angle="90",
                od=2.0,
                channel="3",
                ir_led_intensity=1.0,
            ),
            "4": structs.RawODReading(
                timestamp=timestamp,
                angle="180",
                od=9.0,
                channel="4",
                ir_led_intensity=1.0,
            ),
        },
    )

    aggregated = od_fusion_standards._aggregate_angles(readings)
    assert aggregated == {"45": 2.0, "90": 2.0}


def test_build_chart_metadata_skips_missing_angles() -> None:
    records: list[tuple[pt.PdAngle, float, float]] = [("45", 0.2, 0.3), ("90", 0.4, 0.5)]

    metadata = od_fusion_standards._build_chart_metadata(records)
    assert metadata is not None
    assert metadata["x_label"] == "log10(OD600)"
    assert metadata["y_label"] == "log(Voltage)"

    series = metadata["series"]
    assert isinstance(series, list)
    assert [entry["id"] for entry in series] == [angle for angle in FUSION_ANGLES if angle != "135"]


def test_start_fusion_session_seeds_expected_session_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        od_fusion_standards,
        "get_pioreactor_model",
        lambda: SimpleNamespace(model_name="pioreactor_20ml_XR"),
    )
    monkeypatch.setattr(od_fusion_standards, "is_pio_job_running", lambda _jobs: [False, False])

    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "70"):
        with _temporary_config_section(
            "od_config.photodiode_channel", {"1": "45", "2": "90", "3": "135", "4": "180"}
        ):
            session = od_fusion_standards.start_fusion_session()

    assert session.protocol_name == od_fusion_standards.FusionStandardsODProtocol.protocol_name
    assert session.step_id == "intro"
    assert session.data["channel_angle_map"] == {"1": "45", "2": "90", "3": "135"}
    assert session.data["records"] == []
    assert session.data["standards"] == []


def test_measure_fusion_standard_for_session_filters_executor_payload() -> None:
    def executor(_action: str, _payload: dict[str, object]) -> dict[str, object]:
        return {
            "samples": [
                {"45": "1.0", "90": 2, "180": 99},
                "ignore-me",
                {"135": 3.5},
            ]
        }

    session = CalibrationSession(
        session_id="session-1",
        protocol_name="od_fusion_standards",
        target_device=pt.OD_FUSED_DEVICE,
        status="in_progress",
        step_id="measure_standard",
        data={},
        created_at=utc_iso_timestamp(),
        updated_at=utc_iso_timestamp(),
    )
    ctx = SessionContext(
        session=session,
        mode="ui",
        inputs=SessionInputs(None),
        collected_calibrations=[],
        executor=executor,
    )

    samples = od_fusion_standards._measure_fusion_standard_for_session(ctx, od_value=0.5, rpm=500.0)

    assert samples == [{"45": 1.0, "90": 2.0}, {"135": 3.5}]
