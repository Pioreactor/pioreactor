# -*- coding: utf-8 -*-
import pytest
from pioreactor.utils import local_intermittent_storage
from pioreactor.web import utils as web_utils
from pioreactor.web.utils import is_rate_limited
from pioreactor.web.utils import is_valid_unix_filename
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
