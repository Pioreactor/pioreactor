# -*- coding: utf-8 -*-
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from msgspec.json import encode
from pioreactor import release_archive
from pioreactor.release_archive import build_release_manifest
from pioreactor.release_archive import ReleaseArchiveVerificationError
from pioreactor.release_archive import verify_release_archive


pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen is required")


def create_signed_release_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: str,
    sidecar_files: dict[str, bytes] | None = None,
) -> Path:
    key_path = tmp_path / "release_signing_key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)],
        check=True,
    )
    public_key = (tmp_path / "release_signing_key.pub").read_text(encoding="utf-8").strip()
    monkeypatch.setattr(release_archive, "TRUSTED_RELEASE_SIGNING_PUBLIC_KEY", public_key)

    release_assets = tmp_path / "release_assets"
    release_assets.mkdir()
    files = {
        "CHANGELOG.md": b"changes",
        "pre_update.sh": b"#!/bin/bash\n",
        "update.sh": b"#!/bin/bash\n",
        "post_update.sh": b"#!/bin/bash\n",
        "update.sql": b"",
        f"wheels_{version}.zip": b"wheels",
        f"pioreactor-{version}-py3-none-any.whl": b"wheel",
    }
    for filename, contents in files.items():
        (release_assets / filename).write_bytes(contents)
    for filename, contents in (sidecar_files or {}).items():
        (release_assets / filename).write_bytes(contents)

    manifest = build_release_manifest(version, release_assets)
    manifest_path = release_assets / release_archive.RELEASE_MANIFEST_FILENAME
    manifest_path.write_bytes(encode(manifest))
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(key_path),
            "-n",
            release_archive.RELEASE_SIGNATURE_NAMESPACE,
            str(manifest_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    archive_path = tmp_path / f"release_{version}.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(release_assets.iterdir()):
            archive.write(path, path.name)

    return archive_path


def test_verify_release_archive_accepts_signed_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = create_signed_release_archive(tmp_path, monkeypatch, "26.5.2")

    verify_release_archive(archive_path, expected_version="26.5.2")


def test_verify_release_archive_accepts_signed_sidecar_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = create_signed_release_archive(
        tmp_path,
        monkeypatch,
        "26.5.2",
        sidecar_files={
            "helper.sh": b"#!/bin/bash\n",
            "template.yaml": b"name: example\n",
        },
    )

    verify_release_archive(archive_path, expected_version="26.5.2")


def test_verify_release_archive_rejects_tampered_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = create_signed_release_archive(tmp_path, monkeypatch, "26.5.2")
    tampered_archive_path = tmp_path / "release_26.5.2_tampered.zip"

    with zipfile.ZipFile(archive_path) as source_archive, zipfile.ZipFile(
        tampered_archive_path, "w"
    ) as tampered_archive:
        for info in source_archive.infolist():
            if info.filename == "update.sh":
                tampered_archive.writestr("update.sh", b"#!/bin/bash\necho pwned\n")
            else:
                tampered_archive.writestr(info, source_archive.read(info.filename))

    with pytest.raises(ReleaseArchiveVerificationError, match="does not match the signed manifest"):
        verify_release_archive(tampered_archive_path, expected_version="26.5.2")


def test_verify_release_archive_rejects_unsafe_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = create_signed_release_archive(tmp_path, monkeypatch, "26.5.2")

    with zipfile.ZipFile(archive_path, "a") as archive:
        archive.writestr("../update.sh", b"#!/bin/bash\n")

    with pytest.raises(ReleaseArchiveVerificationError, match="unsafe member"):
        verify_release_archive(archive_path, expected_version="26.5.2")


def test_verify_release_archive_rejects_missing_manifest(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "release_26.5.2.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("update.sh", b"#!/bin/bash\n")

    with pytest.raises(ReleaseArchiveVerificationError, match="missing its signed manifest"):
        verify_release_archive(archive_path, expected_version="26.5.2")
