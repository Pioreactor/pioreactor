# -*- coding: utf-8 -*-
from __future__ import annotations

from json import dumps

import pytest
from pioreactor.cli.pio import get_non_prerelease_tags_of_pioreactor
from pioreactor.cli.pio import get_tag_to_install
from pioreactor.mureq import Response


# Mock the get function
def mock_get(status_code, body):
    response = Response("", status_code, {}, body)
    return response


def test_get_non_prerelease_tags_of_pioreactor(monkeypatch) -> None:
    fake_releases = [
        {"prerelease": False, "tag_name": "22.1.1"},
        {"prerelease": True, "tag_name": "22.2.1rc"},
        {"prerelease": False, "tag_name": "22.2.1"},
        {"prerelease": False, "tag_name": "22.3.1"},
    ]

    def mock_get_request(url, headers):
        return mock_get(200, dumps(fake_releases))

    monkeypatch.setattr("pioreactor.cli.pio.get", mock_get_request)

    result = get_non_prerelease_tags_of_pioreactor("pioreactor/pioreactor")
    assert [str(r) for r in result] == [
        "22.1.1",
        "22.2.1",
        "22.3.1",
    ]

    # Test when response status code is not 200
    def mock_get_bad_request(url, headers):
        return mock_get(404, "")

    monkeypatch.setattr("pioreactor.cli.pio.get", mock_get_bad_request)

    with pytest.raises(Exception):
        get_non_prerelease_tags_of_pioreactor("pioreactor/pioreactor")


def test_get_non_prerelease_tags_of_pioreactor_sorts_calver_correctly(monkeypatch) -> None:
    fake_releases = [
        {"prerelease": False, "tag_name": "23.4.5"},
        {"prerelease": False, "tag_name": "23.4.4"},
        {"prerelease": False, "tag_name": "23.4.15"},
        {"prerelease": False, "tag_name": "22.12.1"},
    ]

    def mock_get_request(url, headers):
        return mock_get(200, dumps(fake_releases))

    monkeypatch.setattr("pioreactor.cli.pio.get", mock_get_request)

    result = get_non_prerelease_tags_of_pioreactor("pioreactor/pioreactor")
    assert [str(r) for r in result] == [
        "22.12.1",
        "23.4.4",
        "23.4.5",
        "23.4.15",
    ]


def test_get_tag_to_install(monkeypatch) -> None:
    monkeypatch.setattr(
        "pioreactor.cli.pio.get_non_prerelease_tags_of_pioreactor",
        lambda _: ["21.12.1", "22.1.1", "22.2.1", "22.3.1", "22.4.1"],
    )
    assert get_tag_to_install("pioreactor/pioreactor", "latest") == "latest"
    assert get_tag_to_install("pioreactor/pioreactor", "22.3.1") == "tags/22.3.1"

    monkeypatch.setattr("pioreactor.version.__version__", "22.2.1")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "tags/22.3.1"

    monkeypatch.setattr("pioreactor.version.__version__", "22.3.1")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "tags/22.4.1"

    monkeypatch.setattr("pioreactor.version.__version__", "22.4.1")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "latest"

    monkeypatch.setattr("pioreactor.version.__version__", "30.4.1")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "latest"

    monkeypatch.setattr("pioreactor.version.__version__", "22.4.1.dev0")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "latest"

    monkeypatch.setattr("pioreactor.version.__version__", "22.4.1rc0")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "latest"

    monkeypatch.setattr("pioreactor.version.__version__", "22.2.1rc0")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "tags/22.3.1"


def test_get_non_prerelease_tags_of_pioreactor_with_no_releases(monkeypatch) -> None:
    # Test with no releases
    fake_releases: list[str] = []

    def mock_get_request(url, headers):
        return mock_get(200, dumps(fake_releases))

    monkeypatch.setattr("pioreactor.cli.pio.get", mock_get_request)

    result = get_non_prerelease_tags_of_pioreactor("pioreactor/pioreactor")
    assert result == []


def test_get_tag_to_install_with_empty_version_history(monkeypatch) -> None:
    # Test with empty version history
    monkeypatch.setattr("pioreactor.cli.pio.get_non_prerelease_tags_of_pioreactor", lambda _: [])
    monkeypatch.setattr("pioreactor.version.__version__", "22.2.1")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "latest"


def test_get_tag_to_install_with_large_version_history(monkeypatch) -> None:
    # Test with a large version history to simulate stress testing
    fake_versions = [f"23.4.{i}" for i in range(1, 1000)]
    monkeypatch.setattr("pioreactor.cli.pio.get_non_prerelease_tags_of_pioreactor", lambda _: fake_versions)
    monkeypatch.setattr("pioreactor.version.__version__", "23.4.500")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "tags/23.4.501"


def test_get_tag_to_install_handles_dev_and_rc_versions(monkeypatch) -> None:
    # Test handling dev and rc versions in the current version
    monkeypatch.setattr(
        "pioreactor.cli.pio.get_non_prerelease_tags_of_pioreactor",
        lambda _: ["21.12.1", "22.1.1", "22.2.1", "22.3.1", "22.4.1"],
    )
    monkeypatch.setattr("pioreactor.version.__version__", "22.4.1.dev10")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "latest"

    monkeypatch.setattr("pioreactor.version.__version__", "22.3.1.rc1")
    assert get_tag_to_install("pioreactor/pioreactor", None) == "tags/22.4.1"
