# -*- coding: utf-8 -*-
import pytest
from pioreactor.utils import local_intermittent_storage
from pioreactor.web import utils as web_utils
from pioreactor.web.utils import is_rate_limited
from pioreactor.web.utils import is_valid_unix_filename
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
