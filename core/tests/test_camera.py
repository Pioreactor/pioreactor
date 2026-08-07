# -*- coding: utf-8 -*-
from __future__ import annotations

import fcntl
import signal
import stat
import subprocess
from collections.abc import Generator
from contextlib import nullcontext
from datetime import datetime
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from msgspec.json import decode as json_decode
from pioreactor.actions.led_intensity import is_led_channel_locked
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.actions.led_intensity import lock_leds_temporarily
from pioreactor.camera import camera_auto_capture_is_enabled
from pioreactor.camera import camera_capture_lock
from pioreactor.camera import camera_focus_preview_path
from pioreactor.camera import camera_hardware_is_detected
from pioreactor.camera import CAMERA_SETTINGS_CACHE_NAME
from pioreactor.camera import camera_should_be_kept_active
from pioreactor.camera import camera_still_image_path
from pioreactor.camera import CAMERA_STILLS_CACHE_NAME
from pioreactor.camera import camera_warmer_runtime_paths
from pioreactor.camera import CameraCaptureError
from pioreactor.camera import CameraStillMetadata
from pioreactor.camera import capture_camera_focus_preview
from pioreactor.camera import capture_camera_still
from pioreactor.camera import clear_camera_hardware_detection_cache
from pioreactor.camera import delete_camera_still
from pioreactor.camera import dev_camera_still_paths
from pioreactor.camera import dev_camera_stills_path
from pioreactor.camera import get_camera_ir_led_intensity
from pioreactor.camera import get_camera_status
from pioreactor.camera import list_camera_still_metadata
from pioreactor.camera import load_camera_still_metadata
from pioreactor.camera import load_latest_camera_still_metadata
from pioreactor.camera import set_camera_auto_capture_enabled
from pioreactor.camera import start_camera_warmer
from pioreactor.camera import stop_camera_warmer
from pioreactor.camera import store_camera_still
from pioreactor.config import ConfigParserMod
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage


def write_source_image(path: Path, contents: bytes = b"fake jpeg") -> None:
    path.write_bytes(contents)


def configure_camera_backend(monkeypatch: pytest.MonkeyPatch, **options: str) -> None:
    camera_config = ConfigParserMod()
    camera_config["camera"] = options
    camera_config["leds_reverse"] = {"IR": "A"}
    monkeypatch.setattr("pioreactor.camera.config", camera_config)


@pytest.fixture(autouse=True)
def clear_camera_stills_metadata() -> Generator[None, None, None]:
    clear_camera_hardware_detection_cache()
    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        storage.empty()
    with local_persistent_storage(CAMERA_SETTINGS_CACHE_NAME) as storage:
        storage.empty()

    yield

    clear_camera_hardware_detection_cache()
    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        storage.empty()
    with local_persistent_storage(CAMERA_SETTINGS_CACHE_NAME) as storage:
        storage.empty()


def test_camera_auto_capture_preference_defaults_to_enabled_and_persists() -> None:
    assert camera_auto_capture_is_enabled() is True
    assert set_camera_auto_capture_enabled(False) is False
    assert camera_auto_capture_is_enabled() is False


def test_camera_capture_lock_uses_lock_file_in_camera_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    lock_operations: list[int] = []
    monkeypatch.setattr(
        "pioreactor.camera.fcntl.flock",
        lambda _file_descriptor, operation: lock_operations.append(operation),
    )

    with camera_capture_lock(dot_pioreactor):
        assert (dot_pioreactor / "storage" / "camera_stills" / ".capture.lock").exists()

    assert lock_operations == [fcntl.LOCK_EX, fcntl.LOCK_UN]


def test_keep_camera_active_defaults_off_and_only_applies_to_rpicam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_camera_backend(monkeypatch, capture_backend="rpicam")
    assert camera_should_be_kept_active() is False

    configure_camera_backend(monkeypatch, capture_backend="v4l2", keep_camera_active="1")
    assert camera_should_be_kept_active() is False

    configure_camera_backend(monkeypatch, capture_backend="rpicam", keep_camera_active="1")
    assert camera_should_be_kept_active() is True


def test_start_camera_warmer_uses_persistent_signal_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor import camera

    configure_camera_backend(
        monkeypatch,
        capture_backend="rpicam",
        camera_index="1",
        keep_camera_active="1",
    )
    monkeypatch.setattr(camera, "CAMERA_WARMER_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(camera, "camera_capture_lock", nullcontext)
    monkeypatch.setattr(camera, "camera_warmer_pid", lambda: None)
    monkeypatch.setattr(camera.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(camera, "sleep", lambda _seconds: None)
    monkeypatch.setattr(camera, "camera_warmer_process", None)
    popen_calls: list[tuple[list[str], dict[str, object]]] = []

    class RunningProcess:
        pid = 123

        def poll(self) -> None:
            return None

    def popen(arguments: list[str], **kwargs: object) -> RunningProcess:
        popen_calls.append((arguments, kwargs))
        return RunningProcess()

    monkeypatch.setattr(camera.subprocess, "Popen", popen)

    assert start_camera_warmer() is True

    pid_path, image_path, latest_path = camera_warmer_runtime_paths()
    assert pid_path.read_text(encoding="utf-8") == "123"
    assert len(popen_calls) == 1
    arguments, _ = popen_calls[0]
    assert arguments[0:3] == ["/usr/bin/rpicam-still", "--camera", "1"]
    assert "--signal" in arguments
    assert arguments[arguments.index("--timeout") + 1] == "0"
    assert arguments[arguments.index("--latest") + 1] == latest_path.as_posix()
    assert arguments[arguments.index("-o") + 1] == image_path.as_posix()
    assert "--immediate" not in arguments


def test_stop_camera_warmer_requests_exit_without_capturing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor import camera

    monkeypatch.setattr(camera, "CAMERA_WARMER_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(camera, "camera_capture_lock", nullcontext)
    monkeypatch.setattr(camera, "camera_warmer_pid", lambda: 123)
    pid_path, _, _ = camera_warmer_runtime_paths()
    pid_path.write_text("123", encoding="utf-8")
    signals: list[tuple[int, int]] = []
    waited: list[float] = []

    class RunningProcess:
        pid = 123

        def wait(self, *, timeout: float) -> None:
            waited.append(timeout)

    monkeypatch.setattr(camera, "camera_warmer_process", RunningProcess())
    monkeypatch.setattr(camera.os, "kill", lambda pid, sig: signals.append((pid, sig)))

    stop_camera_warmer()

    assert signals == [(123, signal.SIGUSR2)]
    assert waited == [5.0]
    assert not pid_path.exists()
    assert camera.camera_warmer_process is None


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
    image_path = camera_still_image_path(metadata)
    assert image_path.read_bytes() == b"fake jpeg"
    assert stat.S_IMODE(image_path.stat().st_mode) == 0o664

    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        assert json_decode(storage["image-1"], type=CameraStillMetadata) == metadata

    assert load_latest_camera_still_metadata("unit-a") == metadata


def test_camera_still_metadata_without_capture_reason_defaults_to_scheduled() -> None:
    metadata = json_decode(
        b'{"experiment":"experiment-a","captured_at":"2026-06-10T12:30:15Z","image_id":"image-1"}',
        type=CameraStillMetadata,
    )

    assert metadata.capture_reason == "scheduled"


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


def test_store_camera_still_retention_preserves_first_and_latest_stills(
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

    assert [metadata.image_id for metadata in list_camera_still_metadata("unit-a")] == ["image-2", "image-0"]
    assert not (dot_pioreactor / "storage" / "camera_stills" / "image-1.jpg").exists()
    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        assert "image-1" not in storage
    assert load_latest_camera_still_metadata("unit-a").image_id == "image-2"


def test_store_camera_still_retention_removes_most_temporally_redundant_still(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    for image_id, minute in (("image-0", 0), ("image-1", 1), ("image-9", 9), ("image-20", 20)):
        store_camera_still(
            source_image_path,
            "unit-a",
            experiment="experiment-a",
            captured_at=datetime(2026, 6, 10, 12, minute, tzinfo=UTC),
            image_id=image_id,
            retention_count=3,
        )

    assert [metadata.image_id for metadata in list_camera_still_metadata("unit-a")] == [
        "image-20",
        "image-9",
        "image-0",
    ]
    assert not (dot_pioreactor / "storage" / "camera_stills" / "image-1.jpg").exists()


def test_store_camera_still_retention_never_deletes_user_requested_stills(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    for image_id, minute, capture_reason in (
        ("automatic-0", 0, "scheduled"),
        ("protected-1", 1, "manual"),
        ("automatic-2", 2, "scheduled"),
        ("automatic-10", 10, "scheduled"),
    ):
        store_camera_still(
            source_image_path,
            "unit-a",
            experiment="experiment-a",
            captured_at=datetime(2026, 6, 10, 12, minute, tzinfo=UTC),
            image_id=image_id,
            capture_reason=capture_reason,
            retention_count=2,
        )

    assert [metadata.image_id for metadata in list_camera_still_metadata("unit-a")] == [
        "automatic-10",
        "protected-1",
        "automatic-0",
    ]
    assert not (dot_pioreactor / "storage" / "camera_stills" / "automatic-2.jpg").exists()
    assert (dot_pioreactor / "storage" / "camera_stills" / "protected-1.jpg").exists()


def test_store_camera_still_retention_is_scoped_to_each_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    for experiment, hour in (("experiment-a", 12), ("experiment-b", 13)):
        for minute in range(3):
            store_camera_still(
                source_image_path,
                "unit-a",
                experiment=experiment,
                captured_at=datetime(2026, 6, 10, hour, minute, tzinfo=UTC),
                image_id=f"{experiment}-{minute}",
                retention_count=2,
            )

    assert [
        metadata.image_id for metadata in list_camera_still_metadata("unit-a", experiment="experiment-a")
    ] == ["experiment-a-2", "experiment-a-0"]
    assert [
        metadata.image_id for metadata in list_camera_still_metadata("unit-a", experiment="experiment-b")
    ] == ["experiment-b-2", "experiment-b-0"]


def test_store_camera_still_requires_capacity_for_first_and_latest_stills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    with pytest.raises(ValueError, match="retention count must be at least 2"):
        store_camera_still(
            source_image_path,
            "unit-a",
            experiment="experiment-a",
            image_id="image-a",
            retention_count=1,
        )

    assert not (dot_pioreactor / "storage" / "camera_stills" / "image-a.jpg").exists()


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


def test_delete_camera_stills_for_experiment_is_idempotent_and_preserves_other_experiments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor import camera

    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("DOT_PIOREACTOR", str(dot_pioreactor))
    source_image_path = tmp_path / "capture.jpg"
    write_source_image(source_image_path)

    experiment_a_still = store_camera_still(
        source_image_path,
        "unit-a",
        experiment="experiment-a",
        image_id="image-a",
        capture_reason="manual",
    )
    experiment_b_still = store_camera_still(
        source_image_path,
        "unit-a",
        experiment="experiment-b",
        image_id="image-b",
    )

    deleted = camera.delete_camera_stills_for_experiment("unit-a", "experiment-a")

    assert deleted == [experiment_a_still]
    assert not camera_still_image_path(experiment_a_still).exists()
    assert camera_still_image_path(experiment_b_still).exists()
    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        assert "image-a" not in storage
        assert "image-b" in storage

    assert camera.delete_camera_stills_for_experiment("unit-a", "experiment-a") == []


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


def test_camera_hardware_detection_returns_false_without_indexed_camera(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        stdout = b"No cameras available!\n"
        stderr = b""

    logger = MagicMock()
    monkeypatch.setattr("pioreactor.camera.subprocess.run", lambda *_args, **_kwargs: Completed())
    monkeypatch.setattr("pioreactor.camera.create_logger", lambda *_args, **_kwargs: logger)

    assert camera_hardware_is_detected("/usr/bin/rpicam-still", 0) is False
    logger.debug.assert_called_once_with(
        "`/usr/bin/rpicam-still --list-cameras` did not report configured camera index 0. "
        "stdout=b'No cameras available!\\n', stderr=b''."
    )


def test_camera_hardware_detection_logs_command_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = MagicMock()
    error = subprocess.CalledProcessError(
        1,
        ["/usr/bin/rpicam-still", "--list-cameras"],
        output=b"partial output",
        stderr=b"camera manager unavailable",
    )
    monkeypatch.setattr("pioreactor.camera.subprocess.run", MagicMock(side_effect=error))
    monkeypatch.setattr("pioreactor.camera.create_logger", lambda *_args, **_kwargs: logger)

    assert camera_hardware_is_detected("/usr/bin/rpicam-still", 0) is False
    logger.debug.assert_called_once_with(
        "`/usr/bin/rpicam-still --list-cameras` exited with code 1 while detecting camera index 0. "
        "stdout=b'partial output', stderr=b'camera manager unavailable'."
    )


def test_camera_hardware_detection_logs_executable_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = MagicMock()
    error = OSError("executable unavailable")
    monkeypatch.setattr("pioreactor.camera.subprocess.run", MagicMock(side_effect=error))
    monkeypatch.setattr("pioreactor.camera.create_logger", lambda *_args, **_kwargs: logger)

    assert camera_hardware_is_detected("/usr/bin/rpicam-still", 0) is False
    logger.debug.assert_called_once_with(
        "Unable to run `/usr/bin/rpicam-still --list-cameras` while detecting camera index 0: "
        "executable unavailable."
    )


def test_camera_hardware_detection_logs_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = MagicMock()
    error = subprocess.TimeoutExpired(
        ["/usr/bin/rpicam-still", "--list-cameras"],
        3.0,
        output=b"partial output",
        stderr=b"still starting",
    )
    monkeypatch.setattr("pioreactor.camera.subprocess.run", MagicMock(side_effect=error))
    monkeypatch.setattr("pioreactor.camera.create_logger", lambda *_args, **_kwargs: logger)

    assert camera_hardware_is_detected("/usr/bin/rpicam-still", 0) is False
    logger.debug.assert_called_once_with(
        "`/usr/bin/rpicam-still --list-cameras` timed out after 3.0 seconds while detecting camera index 0. "
        "stdout=b'partial output', stderr=b'still starting'."
    )


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
    metadata = capture_camera_still("unit-a", experiment="experiment-a", capture_reason="scheduled")

    assert status["available"] is True
    assert status["capture_command"] == "fswebcam"
    assert camera_still_image_path(metadata).read_bytes() == b"webcam still"


def test_rpicam_backend_uses_persistent_process_and_stores_normal_still(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor import camera

    dot_pioreactor = tmp_path / ".pioreactor"
    runtime_dir = tmp_path / "run"
    runtime_dir.mkdir()
    configure_camera_backend(
        monkeypatch,
        capture_backend="rpicam",
        keep_camera_active="1",
        ir_led_intensity="80",
    )
    monkeypatch.setattr(camera, "CAMERA_WARMER_RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(camera, "camera_warmer_pid", lambda: 123)
    monkeypatch.setattr(camera.shutil, "which", lambda _command: "/usr/bin/rpicam-still")
    monkeypatch.setattr(
        camera.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("persistent capture must not launch another process"),
    )
    monkeypatch.setattr(camera, "start_camera_warmer", lambda: True)
    led_states: list[dict[str, float]] = []
    monkeypatch.setattr(
        camera,
        "led_intensity",
        lambda desired_state, **_kwargs: led_states.append(desired_state) or True,
    )
    signals: list[tuple[int, int]] = []

    def signal_camera(pid: int, sig: int) -> None:
        signals.append((pid, sig))
        _, image_path, latest_path = camera_warmer_runtime_paths()
        image_path.write_bytes(b"persistent camera still")
        latest_path.symlink_to(image_path)

    monkeypatch.setattr(camera.os, "kill", signal_camera)

    metadata = capture_camera_still(
        "unit-a",
        experiment="experiment-a",
        capture_reason="scheduled",
        dot_pioreactor=dot_pioreactor,
    )

    assert signals == [(123, signal.SIGUSR1)]
    assert led_states == [{"A": 80.0}, {"A": 0.0}]
    assert camera_still_image_path(metadata, dot_pioreactor).read_bytes() == b"persistent camera still"


def test_rpicam_backend_falls_back_to_one_shot_and_then_starts_warmer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor import camera

    configure_camera_backend(monkeypatch, capture_backend="rpicam", keep_camera_active="1")
    monkeypatch.setattr(camera, "camera_warmer_pid", lambda: None)
    monkeypatch.setattr(camera.shutil, "which", lambda _command: "/usr/bin/rpicam-still")
    monkeypatch.setattr(camera, "led_intensity", lambda *_args, **_kwargs: True)
    capture_commands: list[list[str]] = []

    def capture(arguments: list[str], **_kwargs: object) -> None:
        capture_commands.append(arguments)
        Path(arguments[-1]).write_bytes(b"one-shot camera still")

    warmer_starts: list[bool] = []
    monkeypatch.setattr(camera.subprocess, "run", capture)
    monkeypatch.setattr(camera, "start_camera_warmer", lambda: warmer_starts.append(True) or True)

    metadata = capture_camera_still(
        "unit-a",
        experiment="experiment-a",
        capture_reason="scheduled",
        dot_pioreactor=tmp_path / ".pioreactor",
    )

    assert len(capture_commands) == 1
    assert "--immediate" in capture_commands[0]
    assert warmer_starts == [True]
    assert (
        camera_still_image_path(metadata, tmp_path / ".pioreactor").read_bytes() == b"one-shot camera still"
    )


def test_camera_ir_led_intensity_defaults_to_80(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2")

    assert get_camera_ir_led_intensity() == 80.0


@pytest.mark.parametrize("intensity", [70.0, 100.0])
def test_camera_ir_led_intensity_accepts_bounds(intensity: float, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2", ir_led_intensity=str(intensity))

    assert get_camera_ir_led_intensity() == intensity


@pytest.mark.parametrize("intensity", [69.9, 100.1])
def test_camera_ir_led_intensity_rejects_out_of_range_values(
    intensity: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2", ir_led_intensity=str(intensity))

    with pytest.raises(ValueError, match="between 70 and 100"):
        get_camera_ir_led_intensity()


def test_unlocked_camera_illuminates_ir_during_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_camera_backend(
        monkeypatch,
        capture_backend="v4l2",
        device_path="/dev/video0",
        ir_led_intensity="80",
    )
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda _command: "/usr/bin/fswebcam")
    led_states: list[dict[str, float]] = []

    def set_leds(desired_state: dict[str, float], **_kwargs: object) -> bool:
        led_states.append(desired_state)
        return True

    def capture(command: list[str], **_kwargs: object) -> None:
        Path(command[-1]).write_bytes(b"camera still")

    monkeypatch.setattr("pioreactor.camera.led_intensity", set_leds)
    monkeypatch.setattr("pioreactor.camera.subprocess.run", capture)

    metadata = capture_camera_still(
        "unit-a",
        experiment="experiment-a",
        capture_reason="scheduled",
        dot_pioreactor=tmp_path / ".pioreactor",
    )

    assert led_states == [{"A": 80.0}, {"A": 0.0}]
    assert camera_still_image_path(metadata, tmp_path / ".pioreactor").read_bytes() == b"camera still"


def test_camera_waits_for_od_lock_before_illuminating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2", device_path="/dev/video0")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda _command: "/usr/bin/fswebcam")
    led_states: list[dict[str, float]] = []
    monkeypatch.setattr(
        "pioreactor.camera.led_intensity",
        lambda desired_state, **_kwargs: led_states.append(desired_state) or True,
    )

    def capture(command: list[str], **_kwargs: object) -> None:
        assert not is_led_channel_locked("A")
        Path(command[-1]).write_bytes(b"camera still after OD reading")

    monkeypatch.setattr("pioreactor.camera.subprocess.run", capture)

    od_lock = lock_leds_temporarily(["A"])
    od_lock.__enter__()
    lock_released = False

    def release_od_lock(_seconds: float) -> None:
        nonlocal lock_released
        od_lock.__exit__(None, None, None)
        lock_released = True

    monkeypatch.setattr("pioreactor.camera.sleep", release_od_lock)

    try:
        metadata = capture_camera_still(
            "unit-a",
            experiment="experiment-a",
            capture_reason="scheduled",
            dot_pioreactor=tmp_path / ".pioreactor",
        )
    finally:
        if not lock_released:
            od_lock.__exit__(None, None, None)

    assert led_states == [{"A": 80.0}, {"A": 0.0}]
    assert (
        camera_still_image_path(metadata, tmp_path / ".pioreactor").read_bytes()
        == b"camera still after OD reading"
    )


def test_camera_times_out_waiting_for_od_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2", device_path="/dev/video0")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda _command: "/usr/bin/fswebcam")
    monkeypatch.setattr("pioreactor.camera.monotonic", lambda: 1.0)
    monkeypatch.setattr(
        "pioreactor.camera.led_intensity",
        lambda *_args, **_kwargs: pytest.fail("camera must not illuminate while OD holds the lock"),
    )
    monkeypatch.setattr(
        "pioreactor.camera.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("camera must not capture while OD holds the lock"),
    )

    with lock_leds_temporarily(["A"]):
        with pytest.raises(CameraCaptureError, match="timed out waiting for OD reading"):
            capture_camera_still(
                "unit-a",
                experiment="experiment-a",
                capture_reason="scheduled",
                timeout=0.0,
                dot_pioreactor=tmp_path / ".pioreactor",
            )


def test_od_can_preempt_camera_illumination_without_camera_cleanup_interference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2", device_path="/dev/video0")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda _command: "/usr/bin/fswebcam")
    camera_led_states: list[dict[str, float]] = []
    od_lock = lock_leds_temporarily(["A"])
    lock_owner: str | None = None

    def set_camera_leds(desired_state: dict[str, float], **_kwargs: object) -> bool:
        camera_led_states.append(desired_state)
        return True

    def capture(command: list[str], **_kwargs: object) -> None:
        nonlocal lock_owner
        lock_owner = od_lock.__enter__()
        assert led_intensity({"A": 70.0}, unit="unit-a", experiment="experiment-a", lock_owner=lock_owner)
        assert led_intensity({"A": 0.0}, unit="unit-a", experiment="experiment-a", lock_owner=lock_owner)
        Path(command[-1]).write_bytes(b"possibly spoiled camera still")

    monkeypatch.setattr("pioreactor.camera.led_intensity", set_camera_leds)
    monkeypatch.setattr("pioreactor.camera.subprocess.run", capture)

    try:
        metadata = capture_camera_still(
            "unit-a",
            experiment="experiment-a",
            capture_reason="scheduled",
            dot_pioreactor=tmp_path / ".pioreactor",
        )
        assert camera_led_states == [{"A": 80.0}]
        assert camera_still_image_path(metadata, tmp_path / ".pioreactor").exists()
        with local_intermittent_storage("leds") as cache:
            assert cache.get("A") == 0.0
    finally:
        if lock_owner is not None:
            od_lock.__exit__(None, None, None)


def test_failed_initial_camera_illumination_prevents_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2", device_path="/dev/video0")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda _command: "/usr/bin/fswebcam")
    monkeypatch.setattr("pioreactor.camera.led_intensity", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        "pioreactor.camera.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("camera command must not run without illumination"),
    )

    with pytest.raises(CameraCaptureError, match="illumination could not be started"):
        capture_camera_still(
            "unit-a",
            experiment="experiment-a",
            capture_reason="scheduled",
            dot_pioreactor=tmp_path / ".pioreactor",
        )

    assert list_camera_still_metadata("unit-a", dot_pioreactor=tmp_path / ".pioreactor") == []


def test_failed_camera_cleanup_keeps_captured_still(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2", device_path="/dev/video0")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda _command: "/usr/bin/fswebcam")
    led_results = iter([True, False])
    monkeypatch.setattr("pioreactor.camera.led_intensity", lambda *_args, **_kwargs: next(led_results))

    def capture(command: list[str], **_kwargs: object) -> None:
        Path(command[-1]).write_bytes(b"successful camera still")

    monkeypatch.setattr("pioreactor.camera.subprocess.run", capture)

    metadata = capture_camera_still(
        "unit-a",
        experiment="experiment-a",
        capture_reason="scheduled",
        dot_pioreactor=tmp_path / ".pioreactor",
    )

    assert (
        camera_still_image_path(metadata, tmp_path / ".pioreactor").read_bytes() == b"successful camera still"
    )


def test_camera_command_failure_still_attempts_ir_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_camera_backend(monkeypatch, capture_backend="v4l2", device_path="/dev/video0")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda _command: "/usr/bin/fswebcam")
    led_states: list[dict[str, float]] = []

    def set_leds(desired_state: dict[str, float], **_kwargs: object) -> bool:
        led_states.append(desired_state)
        return True

    def fail_capture(command: list[str], **_kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, command, output=b"", stderr=b"capture failed")

    monkeypatch.setattr("pioreactor.camera.led_intensity", set_leds)
    monkeypatch.setattr("pioreactor.camera.subprocess.run", fail_capture)

    with pytest.raises(CameraCaptureError, match="capture failed"):
        capture_camera_still(
            "unit-a",
            experiment="experiment-a",
            capture_reason="scheduled",
            dot_pioreactor=tmp_path / ".pioreactor",
        )

    assert led_states == [{"A": 80.0}, {"A": 0.0}]


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
    assert "capture_available" not in status
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
    monkeypatch.setattr(
        "pioreactor.camera.led_intensity",
        lambda *_args, **_kwargs: pytest.fail("mock captures must not coordinate IR illumination"),
    )
    source_dir = dev_camera_stills_path()
    source_dir.mkdir(parents=True)
    (source_dir / "still-1.jpg").write_bytes(b"first")
    (source_dir / "still-2.jpg").write_bytes(b"second")

    first = capture_camera_still("unit-a", experiment="experiment-a", capture_reason="scheduled")
    second = capture_camera_still("unit-a", experiment="experiment-a", capture_reason="manual")

    assert camera_still_image_path(first).read_bytes() == b"first"
    assert camera_still_image_path(second).read_bytes() == b"second"
    assert first.capture_reason == "scheduled"
    assert second.capture_reason == "manual"
    assert [metadata.image_id for metadata in list_camera_still_metadata("unit-a")] == [
        second.image_id,
        first.image_id,
    ]


def test_camera_focus_preview_overwrites_one_ephemeral_file_without_still_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dot_pioreactor = tmp_path / ".pioreactor"
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setattr("pioreactor.camera.shutil.which", lambda command: None)
    source_dir = dev_camera_stills_path(dot_pioreactor)
    source_dir.mkdir(parents=True)
    source_image = source_dir / "still-1.jpg"
    source_image.write_bytes(b"first preview")

    first_path = capture_camera_focus_preview(
        "unit-a",
        "session-a",
        dot_pioreactor=dot_pioreactor,
    )
    source_image.write_bytes(b"second preview")
    second_path = capture_camera_focus_preview(
        "unit-a",
        "session-a",
        dot_pioreactor=dot_pioreactor,
    )

    assert first_path == second_path == camera_focus_preview_path("session-a", dot_pioreactor)
    assert second_path.read_bytes() == b"second preview"
    assert stat.S_IMODE(second_path.stat().st_mode) == 0o664
    assert list_camera_still_metadata("unit-a", dot_pioreactor=dot_pioreactor) == []
