# -*- coding: utf-8 -*-
"""
Tests for the get_update_app_commands helper in pioreactor.cli.pio.
"""
import tempfile
from shlex import quote

import click
import pytest
from pioreactor.cli.pio import get_update_app_commands
from pioreactor.config import config


def test_app_commands_with_whl_source() -> None:
    source = "/some/path/pioreactor-1.2.3-py3-none-any.whl"
    cmds, version = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=source,
        version=None,
        defer_web_restart=True,
    )
    assert version == source
    assert cmds == [
        (
            f"/opt/pioreactor/venv/bin/pip install --force-reinstall --no-index {source}",
            1,
        )
    ]


def test_app_commands_with_whl_source_includes_restart_by_default() -> None:
    source = "/some/path/pioreactor-1.2.3-py3-none-any.whl"
    cmds, _ = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=source,
        version=None,
    )
    assert (
        f"/opt/pioreactor/venv/bin/pip install --force-reinstall --no-index {source}",
        1,
    ) in cmds
    assert ("sudo systemctl restart pioreactor-web.target", 30) in cmds


def test_app_commands_with_branch() -> None:
    branch = "feature/test"
    repo = "org/repo"
    cmds, version = get_update_app_commands(
        branch=branch,
        repo=repo,
        source=None,
        version=None,
        defer_web_restart=True,
    )
    assert version == branch
    # Only one command: pip install from monorepo subdirectory=core
    expected = (
        "/opt/pioreactor/venv/bin/pip install --force-reinstall --index-url https://piwheels.org/simple "
        "--extra-index-url https://pypi.org/simple "
        f'"pioreactor[leader_worker] @ git+https://github.com/{repo}.git@{branch}#subdirectory=core"',
        1,
    )
    assert cmds == [expected]


def test_app_commands_with_release_zip(tmp_path) -> None:
    version = "1.2.3"
    # construct a source path matching release zip pattern
    source_path = tmp_path / f"release_{version}.zip"
    # no need to create the file on disk; path string is enough
    source = str(source_path)
    cmds, ver = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=source,
        version=None,
        defer_web_restart=True,
    )
    assert ver == version
    tmp_dir = tempfile.gettempdir()
    tmp_rls_dir = f"{tmp_dir}/release_{version}"
    # verify expected sequence of commands and their priorities
    expected = [
        (f"sudo rm -rf {tmp_rls_dir}", -99),
        (f"unzip -o {source} -d {tmp_rls_dir}", 0),
        (f"unzip -o {tmp_rls_dir}/wheels_{version}.zip -d {tmp_rls_dir}/wheels", 1),
        (f"sudo bash {tmp_rls_dir}/pre_update.sh", 2),
        (f"sudo bash {tmp_rls_dir}/update.sh", 4),
        (f"sudo bash {tmp_rls_dir}/post_update.sh", 20),
        (f"sudo rm -rf {tmp_rls_dir}", 98),
        (
            f"/opt/pioreactor/venv/bin/pip install --no-index --find-links={tmp_rls_dir}/wheels/ "
            f"{tmp_rls_dir}/pioreactor-{version}-py3-none-any.whl[leader,worker]",
            3,
        ),
        (f"sudo sqlite3 {config.get('storage','database')} < {tmp_rls_dir}/update.sql || :", 10),
    ]
    assert cmds == expected


def test_app_commands_invalid_source(capsys) -> None:
    bad_source = "/some/invalid/file.txt"
    with pytest.raises(click.Abort):
        get_update_app_commands(branch=None, repo="org/repo", source=bad_source, version=None)
    captured = capsys.readouterr()
    assert "Not a valid source file" in captured.out


def test_app_commands_branch_with_special_chars() -> None:
    branch = "feature/special branch"
    repo = "org/my repo"
    cmds, ver = get_update_app_commands(
        branch=branch,
        repo=repo,
        source=None,
        version=None,
        defer_web_restart=True,
    )
    cleaned_branch = quote(branch)
    cleaned_repo = quote(repo)
    assert ver == cleaned_branch
    expected_cmd = (
        "/opt/pioreactor/venv/bin/pip install --force-reinstall --index-url https://piwheels.org/simple "
        "--extra-index-url https://pypi.org/simple "
        f'"pioreactor[leader_worker] @ git+https://github.com/{cleaned_repo}.git@{cleaned_branch}#subdirectory=core"'
    )
    assert cmds == [(expected_cmd, 1)]
