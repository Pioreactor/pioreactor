# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from pioreactor.utils import local_intermittent_storage
from pioreactor.web import utils as web_utils
from pioreactor.web.utils import is_rate_limited
from pioreactor.web.utils import is_valid_unix_filename
from pioreactor.web.utils import load_automation_descriptors
from pioreactor.web.utils import load_background_job_descriptors
from pioreactor.web.utils import load_settings_collection_descriptors
from pioreactor.web.utils import scrub_to_valid


def test_none_input_raises() -> None:
    with pytest.raises(ValueError):
        scrub_to_valid(None)  # type: ignore[arg-type]


def test_sqlite_prefixed_input_rejected() -> None:
    with pytest.raises(ValueError):
        scrub_to_valid("sqlite_master")


@pytest.mark.parametrize(
    "dangerous,expected",
    [
        ("users; DROP TABLE users;--", "usersDROPTABLEusers"),
        ("../etc/passwd", "etcpasswd"),
        ("name\x00../../etc/passwd", "nameetcpasswd"),
    ],
)
def test_dangerous_inputs_are_scrubbed(dangerous, expected) -> None:
    assert scrub_to_valid(dangerous) == expected


@pytest.mark.parametrize(
    "name",
    [
        "file.txt",
        "data-set_01",
        "alpha beta-01.ext",
    ],
)
def test_valid_unix_filenames(name) -> None:
    assert is_valid_unix_filename(name)


@pytest.mark.parametrize(
    "name",
    [
        ".hidden",
        "-leadingdash",
        ".",
        "..",
        "dir/file",
        "dir\\file",
        "contains\x1fcontrol",
        "a" * 256,
    ],
)
def test_invalid_unix_filenames(name) -> None:
    assert not is_valid_unix_filename(name)


def test_load_settings_collection_descriptors_reads_ui_settings_and_augments_bioreactor_metadata(
    tmp_path,
) -> None:
    ui_dir = tmp_path / "ui" / "settings"
    ui_dir.mkdir(parents=True)
    (ui_dir / "00_bioreactor.yaml").write_text(
        """\
key: bioreactor
display_name: Bioreactor
display: false
published_settings:
  - key: efflux_tube_volume_ml
    label: Overflow level
    type: numeric
    display: true
  - key: cumulative_media_added_ml
    label: Cumulative media added
    type: numeric
    display: true
  - key: unknown_custom_field
    label: Unknown custom field
    type: numeric
    display: true
""",
        encoding="utf-8",
    )
    (ui_dir / "05_leds.yaml").write_text(
        """\
key: leds
display_name: LED settings
display: false
published_settings:
  - key: intensity
    label: LED intensity
    type: string
    display: true
    editable: false
""",
        encoding="utf-8",
    )

    descriptors = load_settings_collection_descriptors(tmp_path)

    assert [descriptor.key for descriptor in descriptors] == ["bioreactor", "leds"]
    bioreactor_settings = {field.key: field for field in descriptors[0].published_settings}
    assert set(bioreactor_settings) == {"efflux_tube_volume_ml", "cumulative_media_added_ml"}
    assert bioreactor_settings["efflux_tube_volume_ml"].min == 0.0
    assert bioreactor_settings["efflux_tube_volume_ml"].max is None
    assert bioreactor_settings["cumulative_media_added_ml"].default == 0.0
    assert descriptors[1].published_settings[0].editable is False


def test_load_background_job_descriptors_rejects_duplicate_published_settings(
    tmp_path: Path,
) -> None:
    ui_dir = tmp_path / "ui" / "jobs"
    ui_dir.mkdir(parents=True)
    (ui_dir / "duplicate.yaml").write_text(
        """\
display_name: Duplicate
job_name: duplicate
display: true
published_settings:
  - key: repeated
    label: First
    type: numeric
    display: true
  - key: repeated
    label: Second
    type: numeric
    display: true
""",
        encoding="utf-8",
    )
    errors: list[str] = []

    descriptors = load_background_job_descriptors(tmp_path, report_error=errors.append)

    assert descriptors == []
    assert any("Duplicate published setting key: repeated" in error for error in errors)


def test_load_background_job_descriptors_rejects_displayed_setting_without_label(
    tmp_path: Path,
) -> None:
    ui_dir = tmp_path / "ui" / "jobs"
    ui_dir.mkdir(parents=True)
    (ui_dir / "missing-label.yaml").write_text(
        """\
display_name: Missing label
job_name: missing_label
display: true
published_settings:
  - key: target
    type: numeric
    display: true
""",
        encoding="utf-8",
    )
    errors: list[str] = []

    descriptors = load_background_job_descriptors(tmp_path, report_error=errors.append)

    assert descriptors == []
    assert any("requires a label" in error for error in errors)


def test_load_background_job_descriptors_rejects_invalid_min_max(
    tmp_path: Path,
) -> None:
    ui_dir = tmp_path / "ui" / "jobs"
    ui_dir.mkdir(parents=True)
    (ui_dir / "min-max.yaml").write_text(
        """\
display_name: Min max
job_name: min_max
display: true
published_settings:
  - key: target
    label: Target
    type: numeric
    display: true
    min: 10
    max: 1
""",
        encoding="utf-8",
    )
    errors: list[str] = []

    descriptors = load_background_job_descriptors(tmp_path, report_error=errors.append)

    assert descriptors == []
    assert any("min greater than max" in error for error in errors)


def test_load_background_job_descriptors_reports_overrides(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "ui" / "jobs"
    plugin_dir = tmp_path / "plugins" / "ui" / "jobs"
    builtin_dir.mkdir(parents=True)
    plugin_dir.mkdir(parents=True)
    descriptor = """\
display_name: Job
job_name: shared_job
display: false
published_settings: []
"""
    (builtin_dir / "00_builtin.yaml").write_text(descriptor, encoding="utf-8")
    (plugin_dir / "00_plugin.yaml").write_text(
        descriptor.replace("display_name: Job", "display_name: Plugin job"),
        encoding="utf-8",
    )
    errors: list[str] = []

    descriptors = load_background_job_descriptors(tmp_path, report_error=errors.append)

    assert len(descriptors) == 1
    assert descriptors[0].display_name == "Plugin job"
    assert any("overrides job shared_job" in error for error in errors)


def test_load_automation_descriptors_rejects_select_field_without_options(tmp_path: Path) -> None:
    automation_dir = tmp_path / "ui" / "automations" / "dosing"
    automation_dir.mkdir(parents=True)
    (automation_dir / "bad-select.yaml").write_text(
        """\
display_name: Bad select
automation_name: bad_select
description: Bad select
fields:
  - key: mode
    label: Mode
    default: ""
    type: select
""",
        encoding="utf-8",
    )
    errors: list[str] = []

    descriptors = load_automation_descriptors(tmp_path, "dosing", report_error=errors.append)

    assert descriptors == []
    assert any("requires options" in error for error in errors)


def test_load_settings_collection_descriptors_does_not_require_local_model_for_bioreactor_defaults(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pioreactor import bioreactor
    from pioreactor.exc import NoWorkerFoundError

    ui_dir = tmp_path / "ui" / "settings"
    ui_dir.mkdir(parents=True)
    (ui_dir / "00_bioreactor.yaml").write_text(
        """\
key: bioreactor
display_name: Bioreactor
display: true
published_settings:
  - key: current_volume_ml
    label: Current volume
    type: numeric
    display: true
""",
        encoding="utf-8",
    )

    def raise_no_worker_found():
        raise NoWorkerFoundError("Worker debian-testing is not found.")

    monkeypatch.setattr(bioreactor, "get_pioreactor_model", raise_no_worker_found)

    descriptors = load_settings_collection_descriptors(tmp_path)

    assert descriptors[0].published_settings[0].default == pytest.approx(14.0)


def test_is_rate_limited_blocks_second_request_within_window() -> None:
    job_name = "test_rate_limit_second_blocked"
    with local_intermittent_storage("debounce") as cache:
        cache.pop(job_name)

    assert not is_rate_limited(job_name, expire_time_seconds=10.0)
    assert is_rate_limited(job_name, expire_time_seconds=10.0)


def test_is_rate_limited_allows_after_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    job_name = "test_rate_limit_allows_after_expiry"
    with local_intermittent_storage("debounce") as cache:
        cache.pop(job_name)

    timeline = iter([1000.0, 1002.0, 1002.2])
    monkeypatch.setattr(web_utils, "time", lambda: next(timeline))

    assert not is_rate_limited(job_name, expire_time_seconds=1.0)
    assert not is_rate_limited(job_name, expire_time_seconds=1.0)
    assert is_rate_limited(job_name, expire_time_seconds=1.0)
