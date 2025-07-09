# -*- coding: utf-8 -*-
"""
Tests for the get_update_ui_commands helper in pioreactor.cli.pio.
"""
from __future__ import annotations

import json
import os
import tempfile

from pioreactor.cli.pio import get_update_ui_commands


class DummyResponse:
    def __init__(self, body: str) -> None:
        self.body = body


def test_commands_with_source_only() -> None:
    source = "/some/path/archive.tar.gz"
    cmds, version = get_update_ui_commands(branch=None, repo="org/repo", source=source, version=None)
    assert version == source
    assert cmds == [["bash", "/usr/local/bin/update_ui.sh", source]]


def test_commands_with_branch(monkeypatch) -> None:
    branch = "develop"
    repo = "pioreactor/pioreactor"
    cmds, version = get_update_ui_commands(branch=branch, repo=repo, source=None, version=None)
    assert version == branch

    tmp_dir = "/tmp"
    repo_name = repo.split("/")[-1]
    tmp_archive = os.path.join(tmp_dir, f"{repo_name}-{branch}.tar.gz")
    tmp_extract = os.path.join(tmp_dir, f"{repo_name}-{branch}")
    source = os.path.join(tmp_dir, "pioreactorui_archive.tar.gz")
    assert source == "/tmp/pioreactorui_archive.tar.gz"

    expected = [
        ["rm", "-rf", tmp_extract],
        ["wget", "https://github.com/pioreactor/pioreactor/archive/develop.tar.gz", "-O", tmp_archive],
        ["mkdir", "-p", tmp_extract],
        ["tar", "-xzf", tmp_archive, "-C", tmp_dir],
        ["tar", "czf", source, "-C", os.path.join(tmp_extract, "web"), "."],
        ["bash", "/usr/local/bin/update_ui.sh", source],
    ]
    assert cmds == expected


def test_commands_with_version_tag(monkeypatch) -> None:
    version = "v1.2.3"
    repo = "org/repo"
    # stub out GitHub API release fetch
    meta = {"tag_name": version}

    def fake_get(url: str) -> DummyResponse:
        return DummyResponse(json.dumps(meta))

    monkeypatch.setattr("pioreactor.cli.pio.get", fake_get)
    monkeypatch.setattr("pioreactor.cli.pio.loads", lambda b: meta)

    cmds, ver = get_update_ui_commands(branch=None, repo=repo, source=None, version=version)
    assert ver == version

    tmp_dir = tempfile.gettempdir()
    repo_name = repo.split("/")[-1]
    tmp_archive = os.path.join(tmp_dir, f"{repo_name}-{version}.tar.gz")
    tmp_extract = os.path.join(tmp_dir, f"{repo_name}-{version}")
    source = os.path.join(tmp_dir, "pioreactorui_archive.tar.gz")

    expected = [
        ["rm", "-rf", tmp_extract],
        ["wget", f"https://github.com/{repo}/archive/refs/tags/{version}.tar.gz", "-O", tmp_archive],
        ["mkdir", "-p", tmp_extract],
        ["tar", "-xzf", tmp_archive, "-C", tmp_dir],
        ["tar", "czf", source, "-C", os.path.join(tmp_extract, "web"), "."],
        ["bash", "/usr/local/bin/update_ui.sh", source],
    ]
    assert cmds == expected
