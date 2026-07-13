# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from datetime import UTC
from pathlib import Path

import pytest
from msgspec.json import decode as json_decode
from pioreactor.camera import camera_hardware_is_detected
from pioreactor.camera import camera_still_image_path
from pioreactor.camera import CAMERA_STILLS_CACHE_NAME
from pioreactor.camera import CameraStillMetadata
from pioreactor.camera import capture_camera_still
from pioreactor.camera import clear_camera_hardware_detection_cache
from pioreactor.camera import delete_camera_still
from pioreactor.camera import dev_camera_still_paths
from pioreactor.camera import dev_camera_stills_path
from pioreactor.camera import get_camera_status
from pioreactor.camera import list_camera_still_metadata
from pioreactor.camera import load_camera_still_metadata
from pioreactor.camera import load_latest_camera_still_metadata
from pioreactor.camera import store_camera_still
from pioreactor.config import ConfigParserMod
from pioreactor.utils import local_persistent_storage


def write_source_image(path: Path, contents: bytes = b"fake jpeg") -> None:
    path.write_bytes(contents)


def configure_camera_backend(monkeypatch: pytest.MonkeyPatch, **options: str) -> None:
    camera_config = ConfigParserMod()
    camera_config["camera"] = options
    monkeypatch.setattr("pioreactor.camera.config", camera_config)


@pytest.fixture(autouse=True)
def clear_camera_stills_metadata() -> Generator[None, None, None]:
    clear_camera_hardware_detection_cache()
    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        storage.empty()

    yield

    clear_camera_hardware_detection_cache()
    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        storage.empty()


def test_store_camera_still_writes_canonical_image_and_metadata(
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
        captured_at=captured_at,
        image_id="image-1",
    )

    assert metadata == CameraStillMetadata(
        experiment="experiment-a",
        captured_at=captured_at,
        image_id="image-1",
    )
    assert camera_still_image_path(metadata).read_bytes() == b"fake jpeg"

    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        assert json_decode(storage["image-1"], type=CameraStillMetadata) == metadata

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
            captured_at=datetime(2026, 6, 10, 12, i, tzinfo=UTC),
            image_id=f"image-{i}",
            retention_count=2,
        )

    assert [metadata.image_id for metadata in list_camera_still_metadata("unit-a")] == ["image-2", "image-1"]
    assert not (dot_pioreactor / "storage" / "camera_stills" / "image-0.jpg").exists()
    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        assert "image-0" not in storage
    assert load_latest_camera_still_metadata("unit-a").image_id == "image-2"


def test_list_camera_still_metadata_filters_by_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    store_camera_still(
        source_image_path,
        "unit-a",
        experiment="experiment-a",
        captured_at=datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
        image_id="image-a",
    )
    store_camera_still(
        source_image_path,
        "unit-a",
        experiment="experiment-b",
        captured_at=datetime(2026, 6, 10, 12, 1, tzinfo=UTC),
        image_id="image-b",
    )

    assert [
        metadata.image_id for metadata in list_camera_still_metadata("unit-a", experiment="experiment-a")
    ] == ["image-a"]


def test_load_camera_still_metadata_requires_matching_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    metadata = store_camera_still(
        source_image_path,
        "unit-a",
        experiment="experiment-a",
        image_id="image-a",
    )

    assert load_camera_still_metadata("unit-a", "experiment-a", "image-a") == metadata
    assert load_camera_still_metadata("unit-a", "experiment-b", "image-a") is None


def test_delete_camera_still_removes_image_and_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)
    metadata = store_camera_still(
        source_image_path,
        "unit-a",
        experiment="experiment-a",
        image_id="image-a",
    )

    assert delete_camera_still("unit-a", "experiment-a", "image-a") == metadata
    assert not camera_still_image_path(metadata).exists()
    assert load_camera_still_metadata("unit-a", "experiment-a", "image-a") is None
    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        assert "image-a" not in storage


def test_delete_camera_still_requires_matching_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)
    metadata = store_camera_still(
        source_image_path,
        "unit-a",
        experiment="experiment-a",
        image_id="image-a",
    )

    assert delete_camera_still("unit-a", "experiment-b", "image-a") is None
    assert camera_still_image_path(metadata).exists()
    assert load_camera_still_metadata("unit-a", "experiment-a", "image-a") == metadata


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
            image_id="image-1",
        )

    with pytest.raises(ValueError, match="Unsafe camera image id"):
        store_camera_still(
            source_image_path,
            "unit-a",
            experiment=None,
            image_id="../image-1",
        )


def test_camera_hardware_detection_uses_generic_list_cameras_output(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        stdout = b"Available cameras\n-----------------\n0 : ov5647 [2592x1944]\n"
        stderr = b""

    monkeypatch.setattr("pioreactor.camera.subprocess.run", lambda *_args, **_kwargs: Completed())

    assert camera_hardware_is_detected("/usr/bin/rpicam-still", 0) is True
    assert camera_hardware_is_detected("/usr/bin/rpicam-still", 1) is False


def test_camera_hardware_detection_returns_false_without_indexed_camera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        stdout = b"No cameras available!\n"
        stderr = b""

    monkeypatch.setattr("pioreactor.camera.subprocess.run", lambda *_args, **_kwargs: Completed())

    assert camera_hardware_is_detected("/usr/bin/rpicam-still", 0) is False


def test_rpicam_backend_uses_camera_index_and_tuned_capture_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    configure_camera_backend(monkeypatch, capture_backend="rpicam", camera_index="2")
    monkeypatch.setattr(
        "pioreactor.camera.shutil.which",
        lambda command: f"/usr/bin/{command}" if command == "rpicam-still" else None,
    )

    def capture(command: list[str], **_kwargs: object) -> None:
        assert command[:-1] == [
            "/usr/bin/rpicam-still",
            "--camera",
            "2",
            "--nopreview",
            "--immediate",
            "--tuning-file",
            "/usr/share/libcamera/ipa/rpi/vc4/ov5647_noir.json",
            "--mode",
            "2592:1944:10:P",
            "--width",
            "2592",
            "--height",
            "1944",
            "--buffer-count",
            "2",
            "--framerate",
            "0",
            "--shutter",
            "900000",
            "--gain",
            "2",
            "--awbgains",
            "1,1",
            "--brightness",
            "0",
            "--contrast",
            "1.1",
            "--saturation",
            "0",
            "--sharpness",
            "0",
            "--denoise",
            "cdn_hq",
            "--quality",
            "95",
            "-o",
        ]
        Path(command[-1]).write_bytes(b"rpicam still")

    monkeypatch.setattr("pioreactor.camera.subprocess.run", capture)

    metadata = capture_camera_still("unit-a", experiment="experiment-a")

    assert camera_still_image_path(metadata).read_bytes() == b"rpicam still"


def test_v4l2_backend_uses_configured_device_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    configure_camera_backend(monkeypatch, capture_backend="v4l2", device_path="/dev/null")
    monkeypatch.setattr(
        "pioreactor.camera.shutil.which",
        lambda command: "/usr/bin/fswebcam" if command == "fswebcam" else None,
    )

    def capture(command: list[str], **_kwargs: object) -> None:
        assert command[:-1] == [
            "/usr/bin/fswebcam",
            "--device",
            "/dev/null",
            "--no-banner",
        ]
        Path(command[-1]).write_bytes(b"webcam still")

    monkeypatch.setattr("pioreactor.camera.subprocess.run", capture)

    status = get_camera_status("unit-a")
    metadata = capture_camera_still("unit-a", experiment="experiment-a")

    assert status["available"] is True
    assert status["capture_command"] == "fswebcam"
    assert camera_still_image_path(metadata).read_bytes() == b"webcam still"


def test_camera_backend_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_camera_backend(monkeypatch, capture_backend="unknown")

    with pytest.raises(ValueError, match="camera.capture_backend"):
        get_camera_status("unit-a")


def test_rpicam_backend_rejects_negative_camera_index(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_camera_backend(monkeypatch, capture_backend="rpicam", camera_index="-1")

    with pytest.raises(ValueError, match="camera.camera_index"):
        get_camera_status("unit-a")


def test_camera_status_reuses_cached_hardware_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def detect_camera(_capture_command: str, _camera_index: int) -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr("pioreactor.camera.camera_hardware_is_detected", detect_camera)

    first_status = get_camera_status("unit-a")
    second_status = get_camera_status("unit-a")

    assert first_status["available"] is True
    assert second_status["available"] is True
    assert calls == 1


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
    assert load_latest_camera_still_metadata("unit-a").image_id == status["latest_still"]["image_id"]


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

    first = capture_camera_still("unit-a", experiment="experiment-a")
    second = capture_camera_still("unit-a", experiment="experiment-a")

    assert camera_still_image_path(first).read_bytes() == b"first"
    assert camera_still_image_path(second).read_bytes() == b"second"
    assert [metadata.image_id for metadata in list_camera_still_metadata("unit-a")] == [
        second.image_id,
        first.image_id,
    ]
