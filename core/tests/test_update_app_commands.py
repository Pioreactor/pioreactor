# -*- coding: utf-8 -*-
"""
Tests for the get_update_app_commands helper in pioreactor.cli.pio.
"""
import re
import tempfile
from http.client import HTTPMessage
from json import dumps
from pathlib import Path
from shlex import quote

import click
import pytest
from pioreactor.cli.pio import get_update_app_commands
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.mureq import Response


@pytest.fixture(autouse=True)
def ensure_storage_database_configured() -> object:
    if config.has_option("storage", "database"):
        yield
        return

    database_path = str(Path(".pioreactor") / "storage" / "pioreactor.sqlite")
    with temporary_config_change(config, "storage", "database", database_path):
        yield


def mock_release_metadata_response(tag_name: str, assets: list[dict[str, str]]) -> Response:
    release_metadata = {
        "tag_name": tag_name,
        "assets": assets,
    }
    return Response("", 200, HTTPMessage(), dumps(release_metadata).encode())


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


def test_app_commands_with_whl_source_quotes_spaces_in_path() -> None:
    source = "/some path/pioreactor-1.2.3-py3-none-any.whl"
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
            f"/opt/pioreactor/venv/bin/pip install --force-reinstall --no-index {quote(source)}",
            1,
        )
    ]


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


def test_app_commands_with_sha() -> None:
    sha = "a0b1c2d3e4f56789a0b1c2d3e4f56789a0b1c2d3"
    repo = "org/repo"
    cmds, version = get_update_app_commands(
        branch=None,
        sha=sha,
        repo=repo,
        source=None,
        version=None,
        defer_web_restart=True,
    )
    assert version == sha
    expected = (
        "/opt/pioreactor/venv/bin/pip install --force-reinstall --index-url https://piwheels.org/simple "
        "--extra-index-url https://pypi.org/simple "
        f'"pioreactor[leader_worker] @ git+https://github.com/{repo}.git@{sha}#subdirectory=core"',
        1,
    )
    assert cmds == [expected]


def test_app_commands_with_4_char_sha() -> None:
    sha = "a0b1"
    repo = "org/repo"
    cmds, version = get_update_app_commands(
        branch=None,
        sha=sha,
        repo=repo,
        source=None,
        version=None,
        defer_web_restart=True,
    )
    assert version == sha
    expected = (
        "/opt/pioreactor/venv/bin/pip install --force-reinstall --index-url https://piwheels.org/simple "
        "--extra-index-url https://pypi.org/simple "
        f'"pioreactor[leader_worker] @ git+https://github.com/{repo}.git@{sha}#subdirectory=core"',
        1,
    )
    assert cmds == [expected]


def test_app_commands_with_release_zip(tmp_path) -> None:
    version = "26.3.0"
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


def test_app_commands_with_release_zip_with_spaces_in_path(tmp_path) -> None:
    version = "26.3.0"
    source = str(tmp_path / "release bundles" / f"release_{version}.zip")

    cmds, ver = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=source,
        version=None,
        defer_web_restart=True,
    )

    assert ver == version
    assert cmds[1] == (f"unzip -o {quote(source)} -d {tempfile.gettempdir()}/release_{version}", 0)


def test_app_commands_with_release_zip_prerelease_source() -> None:
    version = "26.4.0rc1"
    source = f"/tmp/release_{version}.zip"

    cmds, ver = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=source,
        version=None,
        defer_web_restart=True,
    )

    assert ver == version
    assert any(
        command == f"unzip -o {quote(source)} -d {tempfile.gettempdir()}/release_{version}" and priority == 0
        for command, priority in cmds
    )


def test_app_commands_invalid_source(capsys) -> None:
    bad_source = "/some/invalid/file.txt"
    with pytest.raises(click.Abort):
        get_update_app_commands(branch=None, repo="org/repo", source=bad_source, version=None)
    captured = capsys.readouterr()
    assert "Not a valid source file" in captured.out


def test_app_commands_invalid_sha() -> None:
    with pytest.raises(click.BadParameter):
        get_update_app_commands(
            branch=None,
            sha="not-a-sha",
            repo="org/repo",
            source=None,
            version=None,
        )


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


def test_app_commands_from_release_metadata_include_restart_by_default(monkeypatch) -> None:
    def mock_get(_url: str, **_kwargs) -> Response:
        return mock_release_metadata_response(
            "26.3.0",
            [
                {
                    "name": "release_26.3.0.zip",
                    "browser_download_url": "https://example.com/release_26.3.0.zip",
                }
            ],
        )

    monkeypatch.setattr("pioreactor.cli.pio.get_tag_to_install", lambda _repo, _version: "latest")
    monkeypatch.setattr("pioreactor.mureq.get", mock_get)

    cmds, _ = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=None,
        version=None,
    )

    wget_command = next(command for command, _ in cmds if command.startswith("wget -O "))
    archive_location = wget_command.removeprefix("wget -O ").removesuffix(
        " https://example.com/release_26.3.0.zip"
    )

    assert archive_location.startswith(quote(f"{tempfile.gettempdir()}/pioreactor_update_archive_"))
    assert archive_location.endswith("release_26.3.0.zip")
    assert (f"wget -O {archive_location} https://example.com/release_26.3.0.zip", -100) in cmds
    assert ("sudo systemctl restart pioreactor-web.target", 99) in cmds


def test_app_commands_from_release_metadata_skip_restart_when_deferred(monkeypatch) -> None:
    def mock_get(_url: str, **_kwargs) -> Response:
        return mock_release_metadata_response(
            "26.3.0",
            [
                {
                    "name": "release_26.3.0.zip",
                    "browser_download_url": "https://example.com/release_26.3.0.zip",
                }
            ],
        )

    monkeypatch.setattr("pioreactor.cli.pio.get_tag_to_install", lambda _repo, _version: "latest")
    monkeypatch.setattr("pioreactor.mureq.get", mock_get)

    cmds, _ = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=None,
        version=None,
        defer_web_restart=True,
    )

    assert ("sudo systemctl restart pioreactor-web.target", 99) not in cmds


def test_app_commands_from_release_metadata_uses_release_archive_flow(monkeypatch) -> None:
    version = "26.3.0"

    def mock_get(_url: str, **_kwargs) -> Response:
        return mock_release_metadata_response(
            version,
            [
                {
                    "name": f"release_{version}.zip",
                    "browser_download_url": f"https://example.com/release_{version}.zip",
                },
                {
                    "name": "pioreactor-26.3.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/pioreactor-26.3.0-py3-none-any.whl",
                },
            ],
        )

    monkeypatch.setattr("pioreactor.cli.pio.get_tag_to_install", lambda _repo, _version: "latest")
    monkeypatch.setattr("pioreactor.mureq.get", mock_get)

    cmds, ver = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=None,
        version=None,
        defer_web_restart=True,
    )

    assert ver == version

    wget_command = next(command for command, _ in cmds if command.startswith("wget -O "))
    archive_location = wget_command.removeprefix("wget -O ").removesuffix(
        f" https://example.com/release_{version}.zip"
    )
    tmp_rls_dir = f"{tempfile.gettempdir()}/release_{version}"
    assert archive_location.startswith(quote(f"{tempfile.gettempdir()}/pioreactor_update_archive_"))
    assert archive_location.endswith(f"release_{version}.zip")
    assert cmds == [
        (f"wget -O {archive_location} https://example.com/release_{version}.zip", -100),
        (f"sudo rm -rf {tmp_rls_dir}", -99),
        (f"unzip -o {archive_location} -d {tmp_rls_dir}", 0),
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
        (f"sudo rm -f {archive_location}", 97),
    ]


def test_app_commands_from_release_metadata_requires_release_archive(monkeypatch) -> None:
    def mock_get(_url: str, **_kwargs) -> Response:
        return mock_release_metadata_response(
            "26.3.0",
            [
                {
                    "name": "pioreactor-26.3.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/pioreactor-26.3.0-py3-none-any.whl",
                }
            ],
        )

    monkeypatch.setattr("pioreactor.cli.pio.get_tag_to_install", lambda _repo, _version: "latest")
    monkeypatch.setattr("pioreactor.mureq.get", mock_get)

    with pytest.raises(FileNotFoundError, match="Could not find release_26.3.0.zip"):
        get_update_app_commands(
            branch=None,
            repo="org/repo",
            source=None,
            version=None,
        )


def test_app_commands_with_release_zip_for_worker_excludes_leader_steps(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("pioreactor.cli.pio.whoami.am_I_leader", lambda: False)
    version = "26.3.0"
    source = str(tmp_path / f"release_{version}.zip")

    cmds, ver = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=source,
        version=None,
        defer_web_restart=True,
    )

    assert ver == version
    assert any(command.endswith(f"pioreactor-{version}-py3-none-any.whl[worker]") for command, _ in cmds)
    assert not any("[leader,worker]" in command for command, _ in cmds)
    assert not any("update.sql" in command for command, _ in cmds)


def test_app_commands_from_release_metadata_for_worker_uses_release_archive(monkeypatch) -> None:
    version = "26.4.0rc1"

    def mock_get(_url: str, **_kwargs) -> Response:
        return mock_release_metadata_response(
            version,
            [
                {
                    "name": f"release_{version}.zip",
                    "browser_download_url": f"https://example.com/release_{version}.zip",
                }
            ],
        )

    monkeypatch.setattr("pioreactor.cli.pio.get_tag_to_install", lambda _repo, _version: "latest")
    monkeypatch.setattr("pioreactor.mureq.get", mock_get)
    monkeypatch.setattr("pioreactor.cli.pio.whoami.am_I_leader", lambda: False)

    cmds, ver = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=None,
        version=None,
        defer_web_restart=True,
    )

    assert ver == version
    assert any(command.endswith(f"pioreactor-{version}-py3-none-any.whl[worker]") for command, _ in cmds)
    assert not any("[leader,worker]" in command for command, _ in cmds)
    assert not any("update.sql" in command for command, _ in cmds)


def test_app_commands_from_release_metadata_does_not_fetch_individual_assets(monkeypatch) -> None:
    version = "26.3.0"

    def mock_get(_url: str, **_kwargs) -> Response:
        return mock_release_metadata_response(
            version,
            [
                {
                    "name": f"release_{version}.zip",
                    "browser_download_url": f"https://example.com/release_{version}.zip",
                },
                {
                    "name": "pre_update.sh",
                    "browser_download_url": "https://example.com/pre_update.sh",
                },
                {
                    "name": "update.sh",
                    "browser_download_url": "https://example.com/update.sh",
                },
                {
                    "name": "update.sql",
                    "browser_download_url": "https://example.com/update.sql",
                },
                {
                    "name": "post_update.sh",
                    "browser_download_url": "https://example.com/post_update.sh",
                },
                {
                    "name": "pioreactor-26.3.0-py3-none-any.whl",
                    "browser_download_url": "https://example.com/pioreactor-26.3.0-py3-none-any.whl",
                },
            ],
        )

    monkeypatch.setattr("pioreactor.cli.pio.get_tag_to_install", lambda _repo, _version: "latest")
    monkeypatch.setattr("pioreactor.mureq.get", mock_get)

    cmds, _ = get_update_app_commands(
        branch=None,
        repo="org/repo",
        source=None,
        version=None,
        defer_web_restart=True,
    )

    wget_commands = [command for command, _ in cmds if command.startswith("wget -O ")]
    assert len(wget_commands) == 1
    assert re.fullmatch(
        rf"wget -O {re.escape(tempfile.gettempdir())}/pioreactor_update_archive_[0-9a-f]+_release_{re.escape(version)}\.zip https://example\.com/release_{re.escape(version)}\.zip",
        wget_commands[0],
    )
