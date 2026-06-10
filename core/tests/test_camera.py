# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from datetime import UTC
from pathlib import Path

import pytest
from msgspec.json import decode as json_decode
from pioreactor.camera import camera_hardware_is_detected
from pioreactor.camera import camera_still_image_path
from pioreactor.camera import camera_still_metadata_path
from pioreactor.camera import CameraStillMetadata
from pioreactor.camera import capture_camera_still
from pioreactor.camera import dev_camera_still_paths
from pioreactor.camera import dev_camera_stills_path
from pioreactor.camera import get_camera_status
from pioreactor.camera import latest_camera_still_metadata_path
from pioreactor.camera import list_camera_still_metadata
from pioreactor.camera import load_latest_camera_still_metadata
from pioreactor.camera import store_camera_still
from pioreactor.config import config as pioreactor_config
from pioreactor.config import temporary_config_changes


def write_source_image(path: Path, contents: bytes = b"fake jpeg") -> None:
    path.write_bytes(contents)


def test_store_camera_still_writes_canonical_image_metadata_and_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    captured_at = datetime(2026, 6, 10, 12, 30, 15, tzinfo=UTC)
    metadata = store_camera_still(
        source_image_path,
        "unit-a",
        experiment="experiment-a",
        capture_reason="manual",
        captured_at=captured_at,
        image_id="image-1",
        resolution=(640, 480),
    )

    assert metadata == CameraStillMetadata(
        unit="unit-a",
        experiment="experiment-a",
        captured_at=captured_at,
        image_id="image-1",
        filename="image-1.jpg",
        resolution=(640, 480),
        capture_reason="manual",
        source_path="storage/camera_stills/unit-a/image-1.jpg",
    )
    assert camera_still_image_path(metadata).read_bytes() == b"fake jpeg"

    metadata_path = camera_still_metadata_path("unit-a", "image-1")
    assert json_decode(metadata_path.read_bytes(), type=CameraStillMetadata) == metadata
    assert (
        json_decode(latest_camera_still_metadata_path("unit-a").read_bytes(), type=CameraStillMetadata)
        == metadata
    )
    assert load_latest_camera_still_metadata("unit-a") == metadata


def test_load_latest_camera_still_metadata_returns_none_without_an_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    metadata = store_camera_still(
        source_image_path,
        "unit-a",
        experiment=None,
        capture_reason="diagnostic",
        image_id="image-1",
    )
    camera_still_image_path(metadata).unlink()

    assert load_latest_camera_still_metadata("unit-a") is None


def test_store_camera_still_applies_retention_to_old_stills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    for i in range(3):
        write_source_image(source_image_path, f"image-{i}".encode())
        store_camera_still(
            source_image_path,
            "unit-a",
            experiment="experiment-a",
            capture_reason="manual",
            captured_at=datetime(2026, 6, 10, 12, i, tzinfo=UTC),
            image_id=f"image-{i}",
            retention_count=2,
        )

    assert [metadata.image_id for metadata in list_camera_still_metadata("unit-a")] == ["image-2", "image-1"]
    assert not camera_still_metadata_path("unit-a", "image-0").exists()
    assert not (dot_pioreactor / "storage" / "camera_stills" / "unit-a" / "image-0.jpg").exists()
    assert load_latest_camera_still_metadata("unit-a").image_id == "image-2"


def test_store_camera_still_rejects_unsafe_storage_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    with pytest.raises(ValueError, match="Unsafe camera unit name"):
        store_camera_still(
            source_image_path,
            "../unit-a",
            experiment=None,
            capture_reason="manual",
            image_id="image-1",
        )

    with pytest.raises(ValueError, match="Unsafe camera image id"):
        store_camera_still(
            source_image_path,
            "unit-a",
            experiment=None,
            capture_reason="manual",
            image_id="../image-1",
        )


def test_camera_hardware_detection_uses_generic_list_cameras_output(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        stdout = b"Available cameras\n-----------------\n0 : ov5647 [2592x1944]\n"
        stderr = b""

    monkeypatch.setattr("pioreactor.camera.subprocess.run", lambda *_args, **_kwargs: Completed())

    assert camera_hardware_is_detected("/usr/bin/rpicam-still") is True


def test_camera_hardware_detection_returns_false_without_indexed_camera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        stdout = b"No cameras available!\n"
        stderr = b""

    monkeypatch.setattr("pioreactor.camera.subprocess.run", lambda *_args, **_kwargs: Completed())

    assert camera_hardware_is_detected("/usr/bin/rpicam-still") is False


def test_dev_camera_stills_are_discovered_only_when_testing_is_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    source_dir = dev_camera_stills_path(dot_pioreactor)
    source_dir.mkdir(parents=True)
    (source_dir / "still-1.jpg").write_bytes(b"fake jpeg")

    monkeypatch.delenv("TESTING", raising=False)

    assert dev_camera_still_paths(dot_pioreactor) == ()

    monkeypatch.setenv("TESTING", "1")

    assert dev_camera_still_paths(dot_pioreactor) == (source_dir / "still-1.jpg",)


def test_camera_status_seeds_latest_still_from_dev_camera_stills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda command: None)
    source_dir = dev_camera_stills_path()
    source_dir.mkdir(parents=True)
    (source_dir / "still-1.jpg").write_bytes(b"fake jpeg")

    status = get_camera_status("unit-a")

    assert status["available"] is True
    assert status["capture_available"] is True
    assert status["runtime_available"] is True
    assert status["mock"] is True
    assert status["latest_still"]["capture_reason"] == "dev_mock"
    assert load_latest_camera_still_metadata("unit-a").image_id == status["latest_still"]["image_id"]


def test_camera_status_reports_stream_url_from_configured_cluster_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(command: str) -> str | None:
        return {
            "rpicam-still": "/usr/bin/rpicam-still",
            "rpicam-vid": "/usr/bin/rpicam-vid",
        }.get(command)

    monkeypatch.setattr("pioreactor.camera.shutil.which", fake_which)
    monkeypatch.setattr("pioreactor.camera.camera_hardware_is_detected", lambda command: True)

    with temporary_config_changes(
        pioreactor_config,
        [
            ("cluster.addresses", "unit-a", "unit-a.local"),
            ("ui", "port", "4999"),
            ("ui", "proto", "http"),
        ],
    ):
        status = get_camera_status("unit-a")

    assert status["stream_available"] is True
    assert status["stream_command"] == "rpicam-vid"
    assert status["stream_url"] == "http://unit-a.local:4999/unit_api/camera/stream"


def test_camera_status_uses_resolved_address_for_stream_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(command: str) -> str | None:
        return {
            "rpicam-still": "/usr/bin/rpicam-still",
            "rpicam-vid": "/usr/bin/rpicam-vid",
        }.get(command)

    monkeypatch.setattr("pioreactor.camera.shutil.which", fake_which)
    monkeypatch.setattr("pioreactor.camera.camera_hardware_is_detected", lambda command: True)

    with temporary_config_changes(
        pioreactor_config,
        [
            ("ui", "port", "4999"),
            ("ui", "proto", "http"),
        ],
    ):
        status = get_camera_status("unit-a")

    assert status["stream_available"] is True
    assert status["stream_url"] == "http://unit-a.local:4999/unit_api/camera/stream"


def test_capture_camera_still_uses_dev_camera_stills_when_command_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda command: None)
    source_dir = dev_camera_stills_path()
    source_dir.mkdir(parents=True)
    (source_dir / "still-1.jpg").write_bytes(b"first")
    (source_dir / "still-2.jpg").write_bytes(b"second")

    first = capture_camera_still("unit-a", experiment="experiment-a", capture_reason="manual")
    second = capture_camera_still("unit-a", experiment="experiment-a", capture_reason="manual")

    assert camera_still_image_path(first).read_bytes() == b"first"
    assert camera_still_image_path(second).read_bytes() == b"second"
    assert [metadata.image_id for metadata in list_camera_still_metadata("unit-a")] == [
        second.image_id,
        first.image_id,
    ]
