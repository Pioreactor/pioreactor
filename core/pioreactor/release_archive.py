# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import re
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

from msgspec import Struct
from msgspec import ValidationError
from msgspec.json import decode


RELEASE_MANIFEST_FILENAME = "pioreactor-release-manifest.json"
RELEASE_MANIFEST_SIGNATURE_FILENAME = f"{RELEASE_MANIFEST_FILENAME}.sig"
RELEASE_SIGNATURE_NAMESPACE = "pioreactor-release"
RELEASE_SIGNATURE_IDENTITY = "pioreactor-release"
RELEASE_VERSION_PATTERN = re.compile(r"^\d{2}\.\d{1,2}\.\d+\w{0,6}$")

# Admin setup required before signed release archives can be produced. Generate
# an Ed25519 signing key with ssh-keygen and replace this with the public key.
TRUSTED_RELEASE_SIGNING_PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIP0Yi/+fG6ioKlO0/ahTQYGzSMp5FWSZojv894Ronq17 pioreactor-release-2026-05-16"


class ReleaseArchiveVerificationError(ValueError):
    pass


class ReleaseArchiveManifest(Struct, frozen=True):
    format: Literal[1]
    product: Literal["pioreactor"]
    version: str
    files: dict[str, str]


def build_release_manifest(version: str, release_assets_dir: Path) -> ReleaseArchiveManifest:
    files: dict[str, str] = {}
    for path in sorted(release_assets_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name in {RELEASE_MANIFEST_FILENAME, RELEASE_MANIFEST_SIGNATURE_FILENAME}:
            continue
        files[path.name] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"

    return ReleaseArchiveManifest(format=1, product="pioreactor", version=version, files=files)


def verify_release_archive(
    archive_location: str | Path, expected_version: str | None = None
) -> ReleaseArchiveManifest:
    archive_path = Path(archive_location)
    if not archive_path.exists():
        raise ReleaseArchiveVerificationError(f"Release archive does not exist: {archive_path}")
    if not archive_path.is_file():
        raise ReleaseArchiveVerificationError(f"Release archive is not a file: {archive_path}")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ReleaseArchiveVerificationError("Release archive contains duplicate file names.")

            for info in infos:
                if not is_safe_release_archive_member(info):
                    raise ReleaseArchiveVerificationError(
                        f"Release archive contains an unsafe member: {info.filename}"
                    )

            try:
                manifest_bytes = archive.read(RELEASE_MANIFEST_FILENAME)
                signature_bytes = archive.read(RELEASE_MANIFEST_SIGNATURE_FILENAME)
            except KeyError as exc:
                raise ReleaseArchiveVerificationError(
                    "Release archive is missing its signed manifest."
                ) from exc

            manifest = parse_release_manifest(manifest_bytes)
            verify_release_manifest_signature(manifest_bytes, signature_bytes)
            verify_release_manifest_matches_archive(archive, manifest, expected_version)
            return manifest
    except zipfile.BadZipFile as exc:
        raise ReleaseArchiveVerificationError("Release archive is not a valid zip file.") from exc


def is_safe_release_archive_member(info: zipfile.ZipInfo) -> bool:
    name = info.filename
    path = Path(name)
    unix_mode = (info.external_attr >> 16) & 0o170000
    return bool(
        name
        and not name.startswith(("/", "\\"))
        and "\\" not in name
        and path.name == name
        and ".." not in path.parts
        and not info.is_dir()
        and unix_mode != stat.S_IFLNK
    )


def parse_release_manifest(manifest_bytes: bytes) -> ReleaseArchiveManifest:
    try:
        return decode(manifest_bytes, type=ReleaseArchiveManifest)
    except ValidationError as exc:
        raise ReleaseArchiveVerificationError("Release archive manifest is invalid.") from exc


def verify_release_manifest_signature(manifest_bytes: bytes, signature_bytes: bytes) -> None:
    if TRUSTED_RELEASE_SIGNING_PUBLIC_KEY.startswith("REPLACE_WITH_"):
        raise ReleaseArchiveVerificationError("Release archive signing public key is not configured.")

    with tempfile.TemporaryDirectory(prefix="pioreactor_release_verify_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        allowed_signers_path = tmpdir_path / "allowed_signers"
        signature_path = tmpdir_path / "manifest.sig"
        allowed_signers_path.write_text(
            f"{RELEASE_SIGNATURE_IDENTITY} {TRUSTED_RELEASE_SIGNING_PUBLIC_KEY}\n",
            encoding="utf-8",
        )
        signature_path.write_bytes(signature_bytes)

        try:
            result = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed_signers_path),
                    "-I",
                    RELEASE_SIGNATURE_IDENTITY,
                    "-n",
                    RELEASE_SIGNATURE_NAMESPACE,
                    "-s",
                    str(signature_path),
                ],
                input=manifest_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ReleaseArchiveVerificationError(
                "ssh-keygen is required to verify release archives."
            ) from exc

    if result.returncode != 0:
        raise ReleaseArchiveVerificationError("Release archive manifest signature is invalid.")


def verify_release_manifest_matches_archive(
    archive: zipfile.ZipFile, manifest: ReleaseArchiveManifest, expected_version: str | None
) -> None:
    if expected_version is not None and manifest.version != expected_version:
        raise ReleaseArchiveVerificationError(
            f"Release archive manifest version {manifest.version} does not match {expected_version}."
        )
    if RELEASE_VERSION_PATTERN.fullmatch(manifest.version) is None:
        raise ReleaseArchiveVerificationError(
            f"Release archive manifest version {manifest.version} is not a valid Pioreactor version."
        )

    required_files = {
        "CHANGELOG.md",
        "pre_update.sh",
        "update.sh",
        "post_update.sh",
        "update.sql",
        f"wheels_{manifest.version}.zip",
        f"pioreactor-{manifest.version}-py3-none-any.whl",
    }
    manifest_files = set(manifest.files)
    missing_required_files = sorted(required_files - manifest_files)
    if missing_required_files:
        raise ReleaseArchiveVerificationError(
            "Release archive manifest is missing required files: " + ", ".join(missing_required_files)
        )

    archive_files = set(archive.namelist()) - {
        RELEASE_MANIFEST_FILENAME,
        RELEASE_MANIFEST_SIGNATURE_FILENAME,
    }
    if archive_files != manifest_files:
        raise ReleaseArchiveVerificationError("Release archive contents do not match the signed manifest.")

    for filename, expected_hash in manifest.files.items():
        if not expected_hash.startswith("sha256:"):
            raise ReleaseArchiveVerificationError(
                f"Release archive manifest has an unsupported hash for {filename}."
            )
        actual_hash = f"sha256:{hashlib.sha256(archive.read(filename)).hexdigest()}"
        if actual_hash != expected_hash:
            raise ReleaseArchiveVerificationError(
                f"Release archive member does not match the signed manifest: {filename}"
            )
