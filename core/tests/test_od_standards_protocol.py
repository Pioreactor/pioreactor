# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from typing import cast
from typing import Iterator

import pytest
from msgspec import convert
from msgspec.json import decode
from msgspec.json import encode
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs import od_reading
from pioreactor.background_jobs import stirring
from pioreactor.calibrations.protocols import od_standards
from pioreactor.calibrations.session_flow import advance_session
from pioreactor.calibrations.session_flow import get_session_step
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionInputs
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name


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


def test_start_standards_session_clears_stale_ir_led_reference_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(od_standards, "is_pio_job_running", lambda _jobs: [False, False])
    testing_experiment = get_testing_experiment_name()
    with local_persistent_storage("ir_led_reference_normalization") as cache:
        cache[testing_experiment] = 1e-5

    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "70"):
        with _temporary_config_section(
            "od_config.photodiode_channel", {"1": od_standards.REF_keyword, "2": "90"}
        ):
            session = od_standards.start_standards_session("od90")
            assert session.data["experiment"] == testing_experiment

    with local_persistent_storage("ir_led_reference_normalization") as cache:
        assert testing_experiment not in cache


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


def _dummy_session() -> CalibrationSession:
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id="session-od-1",
        protocol_name=od_standards.StandardsODProtocol.protocol_name,
        target_device="od",
        status="in_progress",
        step_id="intro",
        data={"experiment": get_testing_experiment_name()},
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize("rpm", [0, 500])
def test_measurement_steps_show_stirring_only_for_positive_rpm(rpm: float) -> None:
    session = _dummy_session()
    session.data.update(
        {
            "channel_angle_map": {"1": "90"},
            "od600_values": [],
            "voltages_by_channel": {"1": []},
            "rpm": rpm,
            "sample_count": 2,
            "standard_index": 1,
        }
    )
    ctx = SessionContext(
        session=session,
        mode="ui",
        inputs=SessionInputs(None),
        collected_calibrations=[],
    )

    standard_step = od_standards.MeasureStandard().render(ctx)
    blank_step = od_standards.MeasureBlank().render(ctx)
    assert standard_step.metadata["primary_action_label"] == "Measure standard"
    assert blank_step.metadata["primary_action_label"] == "Measure blank"
    assert bool(standard_step.metadata["loading_images"]) == (rpm > 0)
    assert bool(blank_step.metadata["loading_images"]) == (rpm > 0)


def test_on_session_abort_requests_od_job_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bytes, int]] = []

    def fake_publish(topic: str, message: bytes, qos: int) -> None:
        calls.append((topic, message, qos))

    monkeypatch.setattr(od_standards, "publish", fake_publish)
    session = _dummy_session()
    session.data["experiment"] = "_testing_original"

    def unavailable_leader() -> str:
        raise AssertionError("Abort must not look up the experiment over the network")

    monkeypatch.setattr(od_standards, "get_testing_experiment_name", unavailable_leader)
    od_standards.StandardsODProtocol.on_session_abort(session)

    assert calls == [
        (
            f"pioreactor/{od_standards.get_unit_name()}/_testing_original/od_reading/$state/set",
            b"disconnected",
            1,
        ),
        (
            f"pioreactor/{od_standards.get_unit_name()}/_testing_original/stirring/$state/set",
            b"disconnected",
            1,
        ),
    ]


def test_on_session_abort_aggregates_cleanup_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_publish(topic: str, message: bytes, qos: int) -> None:
        job_name = topic.split("/")[-3]
        raise RuntimeError(f"failed {job_name}")

    monkeypatch.setattr(od_standards, "publish", failing_publish)
    with pytest.raises(RuntimeError, match="failed od_reading"):
        od_standards.StandardsODProtocol.on_session_abort(_dummy_session())


def test_session_measurement_uses_captured_experiment(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _dummy_session()
    session.data["experiment"] = "_testing_original"
    calls: list[dict] = []

    def execute(action: str, payload: dict) -> dict:
        assert action == "od_standards_measure"
        calls.append(payload)
        return {"voltages": {"2": 0.2}}

    ctx = SessionContext(
        session=session,
        mode="ui",
        inputs=SessionInputs(None),
        collected_calibrations=[],
        executor=execute,
    )
    assert od_standards._measure_standard_for_session(ctx, 500, {"2": "90"}) == {"2": 0.2}
    assert calls[0]["experiment"] == "_testing_original"


@pytest.mark.parametrize("fail_on_read", [None, 5])
def test_snapshot_keeps_warmup_waits_and_averages_three_consecutive_readings(
    monkeypatch: pytest.MonkeyPatch, fail_on_read: int | None
) -> None:
    events: list[str | float] = []
    sample_values = iter([9.0, 8.0, 7.0, 0.1, 0.2, 0.6])
    timestamp = current_utc_datetime()

    class FakeODReader:
        def __init__(self) -> None:
            self.read_count = 0

        def record_from_adc(self) -> structs.ODReadings:
            self.read_count += 1
            events.append(f"read {self.read_count}")
            if self.read_count == fail_on_read:
                raise RuntimeError("ADC failed")
            value = next(sample_values)
            return structs.ODReadings(
                timestamp=timestamp,
                ods={
                    "2": structs.RawODReading(
                        timestamp=timestamp, od=value, angle="90", channel="2", ir_led_intensity=80
                    ),
                    "3": structs.RawODReading(
                        timestamp=timestamp, od=value * 2, angle="135", channel="3", ir_led_intensity=80
                    ),
                },
            )

    @contextmanager
    def start_od_reading(channels: Any, **kwargs: Any) -> Iterator[FakeODReader]:
        assert kwargs["interval"] is None
        assert kwargs["experiment"] == "_testing_snapshot"
        assert kwargs["calibration"] is False
        assert kwargs["estimator"] is False
        events.append("open")
        try:
            yield FakeODReader()
        finally:
            events.append("close")

    monkeypatch.setattr(od_reading, "start_od_reading", start_od_reading)
    monkeypatch.setattr(od_standards, "is_testing_env", lambda: False)
    monkeypatch.setattr(od_standards, "sleep", events.append)

    if fail_on_read is None:
        result = od_standards._read_voltages_from_adc({"2": "90", "3": "135"}, "_testing_snapshot")
        assert result == pytest.approx({"2": 0.3, "3": 0.6})
    else:
        with pytest.raises(RuntimeError, match="ADC failed"):
            od_standards._read_voltages_from_adc({"2": "90", "3": "135"}, "_testing_snapshot")
    expected_reads = [f"read {i}" for i in range(4, (fail_on_read or 6) + 1)]
    assert events == ["open", "read 1", 1.0, "read 2", 1.0, "read 3", 1.0, *expected_reads, "close"]


def test_zero_rpm_measures_without_starting_stirring_or_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    readings = {"2": 0.123456789}
    calls: list[tuple[dict, str]] = []

    def no_stirring(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("0 RPM must not start stirring")

    def no_settling(delay: float) -> None:
        raise AssertionError("0 RPM must not wait for stirring to settle")

    def read_voltages(channel_angle_map: dict, experiment: str) -> dict:
        calls.append((channel_angle_map, experiment))
        return readings

    monkeypatch.setattr(stirring, "start_stirring", no_stirring)
    monkeypatch.setattr(od_standards, "sleep", no_settling)
    monkeypatch.setattr(od_standards, "_read_voltages_from_adc", read_voltages)
    monkeypatch.setattr(od_standards, "is_testing_env", lambda: False)

    assert od_standards._measure_standard(0, {"2": "90"}, "_testing_original") == readings
    assert calls == [({"2": "90"}, "_testing_original")]


@pytest.mark.parametrize("measurement_fails", [False, True])
def test_positive_rpm_settles_and_cleans_up_stirring(
    monkeypatch: pytest.MonkeyPatch, measurement_fails: bool
) -> None:
    events: list[str] = []

    class FakeStirrer:
        def block_until_rpm_is_close_to_target(self, abs_tolerance: float) -> bool:
            assert abs_tolerance == 120
            events.append("converge")
            return True

    @contextmanager
    def start_stirring(target_rpm: float, unit: str, experiment: str) -> Iterator[FakeStirrer]:
        assert target_rpm == 500
        assert unit == od_standards.get_unit_name()
        assert experiment == "_testing_original"
        events.append("start")
        try:
            yield FakeStirrer()
        finally:
            events.append("stop")

    def settle(delay: float) -> None:
        assert delay == 1.0
        events.append("settle")

    def read_voltages(channel_angle_map: dict, experiment: str) -> dict:
        assert channel_angle_map == {"2": "90"}
        assert experiment == "_testing_original"
        events.append("measure")
        if measurement_fails:
            raise RuntimeError("ADC failed")
        return {"2": 0.1}

    monkeypatch.setattr(stirring, "start_stirring", start_stirring)
    monkeypatch.setattr(od_standards, "sleep", settle)
    monkeypatch.setattr(od_standards, "_read_voltages_from_adc", read_voltages)
    monkeypatch.setattr(od_standards, "is_testing_env", lambda: False)

    if measurement_fails:
        with pytest.raises(RuntimeError, match="ADC failed"):
            od_standards._measure_standard(500, {"2": "90"}, "_testing_original")
    else:
        assert od_standards._measure_standard(500, {"2": "90"}, "_testing_original") == {"2": 0.1}
    assert events == ["start", "converge", "settle", "measure", "stop"]


@pytest.mark.parametrize("target_device", ["od90", "od"])
@pytest.mark.parametrize("blank_od600", [0.0, 0.05])
@pytest.mark.parametrize("rpm", [0, 500])
@pytest.mark.parametrize("sample_count", [2, 4])
def test_blank_first_flow_saves_each_channel_anchored_to_the_blank(
    monkeypatch: pytest.MonkeyPatch,
    target_device: pt.ODCalibrationDevices,
    blank_od600: float,
    rpm: float,
    sample_count: int,
) -> None:
    monkeypatch.setattr(od_standards, "is_pio_job_running", lambda _jobs: [False, False])
    monkeypatch.setattr(od_standards, "list_of_calibrations_by_device", lambda _device: [])
    registry = od_standards._OD_STANDARDS_STEPS
    saved: list[dict[str, Any]] = []
    measured: list[str] = []

    def execute(action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "od_standards_measure":
            assert payload["rpm"] == rpm
            measured.append(session.step_id)
            scale = 0.001 if len(measured) == 1 else 0.1 * (len(measured) - 1)
            return {
                "voltages": {channel: int(channel) * scale for channel in session.data["channel_angle_map"]}
            }
        assert action == "save_calibration"
        saved.append(payload)
        return {"path": f"/tmp/{payload['device']}.yaml"}

    with _temporary_config_section("od_config.photodiode_channel", {"1": "REF", "2": "90", "3": "135"}):
        session = od_standards.start_standards_session(target_device)
    assert session.data["blank_index"] is None
    session = advance_session(registry, session, {}, execute)
    session = advance_session(registry, session, {"calibration_name": "blank-first"}, execute)
    if target_device == "od":
        assert session.step_id == "channel_confirm"
        session = advance_session(registry, session, {}, execute)
    assert session.step_id == "setup"
    session = advance_session(registry, session, {"rpm": rpm, "sample_count": sample_count}, execute)
    assert session.step_id == "place_blank"
    session = advance_session(registry, session, {}, execute)
    assert session.step_id == "measure_blank"
    session = advance_session(registry, session, {"od600_blank": blank_od600}, execute)
    assert session.step_id == "place_standard"
    assert session.data["blank_index"] == 0
    for index in range(1, sample_count):
        assert session.step_id == "place_standard"
        step = get_session_step(registry, session, execute)
        assert step.title == f"Place standard {index} of {sample_count - 1}"
        assert "actions" not in step.metadata
        session = advance_session(registry, session, {}, execute)
        step = get_session_step(registry, session, execute)
        assert step.title == f"Record standard {index} of {sample_count - 1}"
        if index == 1:
            assert step.metadata["table"]["rows"] == [["Blank", blank_od600]]
        session = advance_session(registry, session, {"od600_value": 0.5 * index}, execute)
    assert session.step_id == "review_data"
    # Simulate resuming a persisted UI session before saving.
    session = decode(encode(session), type=CalibrationSession)
    review = get_session_step(registry, session, execute)
    assert [row["standard"] for row in review.fields[0].default] == [
        "Blank",
        *[str(index) for index in range(1, sample_count)],
    ]
    session = advance_session(registry, session, {"recorded_data": review.fields[0].default}, execute)
    assert session.status == "complete"
    assert measured == ["measure_blank", *["measure_standard"] * (sample_count - 1)]
    assert {cal["device"] for cal in saved} == ({"od90", "od135"} if target_device == "od" else {"od90"})
    for payload in saved:
        calibration = convert(payload["calibration"], type=structs.OD600Calibration)
        assert calibration.recorded_data["x"] == [blank_od600, *[0.5 * i for i in range(1, sample_count)]]
        assert calibration.x_to_y(blank_od600) == pytest.approx(calibration.recorded_data["y"][0])


@pytest.mark.parametrize("sample_count", [0, 1, -1, 2.5, "2.5", ""])
def test_setup_requires_a_whole_sample_count_including_blank(sample_count: object) -> None:
    session = _dummy_session()
    session.step_id = "setup"
    session.data["rpm"] = 500
    with pytest.raises(ValueError):
        advance_session(
            od_standards._OD_STANDARDS_STEPS,
            session,
            {"sample_count": sample_count, "rpm": 500},
        )
    assert session.step_id == "setup"
    assert "sample_count" not in session.data
