# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from datetime import UTC
from fcntl import flock
from fcntl import LOCK_EX
from fcntl import LOCK_NB
from fcntl import LOCK_UN
from pathlib import Path
from typing import Annotated
from typing import BinaryIO

from msgspec import Meta
from msgspec import Struct
from msgspec import to_builtins
from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode
from pioreactor import types as pt
from pioreactor.config import config
from pioreactor.pubsub import create_webserver_path
from pioreactor.utils.networking import resolve_to_address
from pioreactor.whoami import is_testing_env


CAMERA_STILLS_RELATIVE_DIR = Path("storage") / "camera_stills"
CAMERA_STILL_CONTENT_TYPE = "image/jpeg"
CAMERA_STREAM_CONTENT_TYPE = "multipart/x-mixed-replace; boundary=frame"
DEFAULT_CAMERA_STILL_RETENTION_COUNT = 200
LATEST_CAMERA_STILL_METADATA_FILENAME = "latest.json"
CAMERA_CAPTURE_COMMANDS = ("rpicam-still", "libcamera-still")
CAMERA_STREAM_COMMANDS = ("rpicam-vid", "libcamera-vid")
DEV_CAMERA_STILLS_DIRNAME = "DEV_CAMERA_STILLS"
CAMERA_LOCK_FILENAME = "camera.lock"
CAMERA_STREAM_BOUNDARY = b"frame"
DEFAULT_CAMERA_STREAM_FPS = 5
DEFAULT_CAMERA_STREAM_WIDTH = 640
DEFAULT_CAMERA_STREAM_HEIGHT = 480

SAFE_CAMERA_STORAGE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class CameraStillMetadata(Struct, frozen=True):
    unit: pt.Unit
    experiment: pt.Experiment | None
    captured_at: Annotated[datetime, Meta(tz=True)]
    image_id: str
    filename: str
    resolution: tuple[int, int] | None
    capture_reason: str
    source_path: str
    content_type: str = CAMERA_STILL_CONTENT_TYPE


class CameraUnavailableError(RuntimeError):
    pass


class CameraCaptureError(RuntimeError):
    pass


class CameraBusyError(RuntimeError):
    pass


def resolve_dot_pioreactor_path() -> Path:
    if "DOT_PIOREACTOR" in os.environ:
        return Path(os.environ["DOT_PIOREACTOR"])

    if is_testing_env():
        return Path(".pioreactor")

    return Path("/home/pioreactor/.pioreactor")


def camera_stills_root_path(dot_pioreactor: Path | None = None) -> Path:
    root = dot_pioreactor if dot_pioreactor is not None else resolve_dot_pioreactor_path()
    return root / CAMERA_STILLS_RELATIVE_DIR


def camera_storage_root_path(dot_pioreactor: Path | None = None) -> Path:
    root = dot_pioreactor if dot_pioreactor is not None else resolve_dot_pioreactor_path()
    return root / "storage"


def dev_camera_stills_path(dot_pioreactor: Path | None = None) -> Path:
    return camera_stills_root_path(dot_pioreactor) / DEV_CAMERA_STILLS_DIRNAME


def camera_stills_unit_path(unit: pt.Unit, dot_pioreactor: Path | None = None) -> Path:
    if not camera_storage_name_is_safe(unit):
        raise ValueError(f"Unsafe camera unit name: {unit}")

    return camera_stills_root_path(dot_pioreactor) / unit


def camera_storage_name_is_safe(value: str) -> bool:
    return bool(SAFE_CAMERA_STORAGE_NAME.fullmatch(value))


def create_camera_image_id(captured_at: datetime | None = None) -> str:
    captured_at = captured_at or datetime.now(UTC)

    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)

    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def find_camera_capture_command() -> str | None:
    for command in CAMERA_CAPTURE_COMMANDS:
        resolved = shutil.which(command)
        if resolved:
            return resolved

    return None


def find_camera_stream_command() -> str | None:
    for command in CAMERA_STREAM_COMMANDS:
        resolved = shutil.which(command)
        if resolved:
            return resolved

    return None


def get_camera_stream_url(unit: pt.Unit) -> str:
    return create_webserver_path(resolve_to_address(unit), "/unit_api/camera/stream")


def get_camera_stream_fps() -> int:
    return max(1, config.getint("ui.camera", "stream_fps", fallback=DEFAULT_CAMERA_STREAM_FPS))


def get_camera_stream_width() -> int:
    return max(1, config.getint("ui.camera", "stream_width", fallback=DEFAULT_CAMERA_STREAM_WIDTH))


def get_camera_stream_height() -> int:
    return max(1, config.getint("ui.camera", "stream_height", fallback=DEFAULT_CAMERA_STREAM_HEIGHT))


def acquire_camera_operation_lock(dot_pioreactor: Path | None = None) -> BinaryIO:
    lock_dir = camera_storage_root_path(dot_pioreactor)
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = (lock_dir / CAMERA_LOCK_FILENAME).open("a+b")

    try:
        flock(lock_file.fileno(), LOCK_EX | LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        raise CameraBusyError("Another camera operation is already running.")

    return lock_file


def release_camera_operation_lock(lock_file: BinaryIO) -> None:
    flock(lock_file.fileno(), LOCK_UN)
    lock_file.close()


@contextmanager
def camera_operation_lock(dot_pioreactor: Path | None = None) -> Iterator[None]:
    lock_file = acquire_camera_operation_lock(dot_pioreactor)
    try:
        yield
    finally:
        release_camera_operation_lock(lock_file)


def dev_camera_still_paths(dot_pioreactor: Path | None = None) -> tuple[Path, ...]:
    if os.environ.get("TESTING") != "1":
        return ()

    source_dir = dev_camera_stills_path(dot_pioreactor)

    if not source_dir.exists():
        return ()

    return tuple(
        sorted(
            path
            for path in source_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
        )
    )


def dev_camera_stills_are_available(dot_pioreactor: Path | None = None) -> bool:
    return bool(dev_camera_still_paths(dot_pioreactor))


def store_next_dev_camera_still(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None,
    capture_reason: str,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata | None:
    source_paths = dev_camera_still_paths(dot_pioreactor)
    if not source_paths:
        return None

    index = len(list_camera_still_metadata(unit, dot_pioreactor)) % len(source_paths)
    return store_camera_still(
        source_paths[index],
        unit,
        experiment=experiment,
        capture_reason=capture_reason,
        dot_pioreactor=dot_pioreactor,
    )


def camera_hardware_is_detected(capture_command: str, timeout: float = 3.0) -> bool:
    try:
        result = subprocess.run(
            [capture_command, "--list-cameras"],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    output = (
        result.stdout.decode("utf-8", errors="replace")
        + "\n"
        + result.stderr.decode("utf-8", errors="replace")
    )

    return bool(re.search(r"(?m)^\s*\d+\s*:", output))


def get_camera_status(unit: pt.Unit, dot_pioreactor: Path | None = None) -> dict[str, object]:
    capture_command = find_camera_capture_command()
    stream_command = find_camera_stream_command()
    dev_stills_available = dev_camera_stills_are_available(dot_pioreactor)
    detection_command = capture_command or stream_command
    camera_detected = (
        camera_hardware_is_detected(detection_command) if detection_command is not None else False
    ) or dev_stills_available
    latest_metadata = load_latest_camera_still_metadata(unit, dot_pioreactor)
    if latest_metadata is None and dev_stills_available:
        latest_metadata = store_next_dev_camera_still(
            unit,
            experiment=None,
            capture_reason="dev_mock",
            dot_pioreactor=dot_pioreactor,
        )

    stream_url = get_camera_stream_url(unit)
    stream_available = camera_detected and stream_command is not None

    return {
        "unit": unit,
        "available": camera_detected,
        "runtime_available": (capture_command is not None)
        or (stream_command is not None)
        or dev_stills_available,
        "capture_available": camera_detected and ((capture_command is not None) or dev_stills_available),
        "stream_available": stream_available,
        "capture_command": Path(capture_command).name if capture_command else None,
        "stream_command": Path(stream_command).name if stream_command else None,
        "stream_url": stream_url if stream_available else None,
        "mock": dev_stills_available and capture_command is None,
        "latest_still": to_builtins(latest_metadata) if latest_metadata is not None else None,
    }


def capture_camera_still(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None,
    capture_reason: str,
    timeout: float = 20.0,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata:
    command = find_camera_capture_command()

    with camera_operation_lock(dot_pioreactor):
        if command is None:
            dev_still = store_next_dev_camera_still(
                unit,
                experiment=experiment,
                capture_reason=capture_reason,
                dot_pioreactor=dot_pioreactor,
            )
            if dev_still is not None:
                return dev_still

            raise CameraUnavailableError("No Raspberry Pi camera capture command is installed.")

        with tempfile.NamedTemporaryFile(prefix="pioreactor-camera-", suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            result = subprocess.run(
                [command, "-n", "--timeout", "1000", "-o", tmp_path.as_posix()],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                stdout = result.stdout.decode("utf-8", errors="replace").strip()
                message = stderr or stdout or f"{Path(command).name} exited with code {result.returncode}"
                raise CameraCaptureError(message)

            return store_camera_still(
                tmp_path,
                unit,
                experiment=experiment,
                capture_reason=capture_reason,
                dot_pioreactor=dot_pioreactor,
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


def create_camera_mjpeg_stream(lock_file: BinaryIO) -> Iterator[bytes]:
    command = find_camera_stream_command()
    if command is None:
        release_camera_operation_lock(lock_file)
        raise CameraUnavailableError("No Raspberry Pi camera stream command is installed.")

    try:
        process = subprocess.Popen(
            [
                command,
                "-n",
                "--timeout",
                "0",
                "--codec",
                "mjpeg",
                "--inline",
                "--framerate",
                str(get_camera_stream_fps()),
                "--width",
                str(get_camera_stream_width()),
                "--height",
                str(get_camera_stream_height()),
                "-o",
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        release_camera_operation_lock(lock_file)
        raise CameraUnavailableError(str(e)) from e

    def stream() -> Iterator[bytes]:
        buffer = b""
        try:
            if process.stdout is None:
                raise CameraCaptureError("Camera stream did not provide stdout.")

            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break

                buffer += chunk
                while True:
                    start = buffer.find(b"\xff\xd8")
                    if start == -1:
                        buffer = buffer[-1:]
                        break

                    end = buffer.find(b"\xff\xd9", start + 2)
                    if end == -1:
                        buffer = buffer[start:]
                        break

                    frame = buffer[start : end + 2]
                    buffer = buffer[end + 2 :]
                    yield (
                        b"--"
                        + CAMERA_STREAM_BOUNDARY
                        + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(frame)).encode("ascii")
                        + b"\r\n\r\n"
                        + frame
                        + b"\r\n"
                    )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            release_camera_operation_lock(lock_file)

    return stream()


def store_camera_still(
    source_image_path: Path,
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None,
    capture_reason: str,
    captured_at: datetime | None = None,
    image_id: str | None = None,
    resolution: tuple[int, int] | None = None,
    retention_count: int = DEFAULT_CAMERA_STILL_RETENTION_COUNT,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata:
    if not source_image_path.exists():
        raise FileNotFoundError(source_image_path)

    captured_at = captured_at or datetime.now(UTC)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)
    captured_at = captured_at.astimezone(UTC)

    image_id = image_id or create_camera_image_id(captured_at)
    if not camera_storage_name_is_safe(image_id):
        raise ValueError(f"Unsafe camera image id: {image_id}")

    unit_dir = camera_stills_unit_path(unit, dot_pioreactor)
    unit_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{image_id}.jpg"
    destination_image_path = unit_dir / filename
    shutil.copyfile(source_image_path, destination_image_path)

    root = dot_pioreactor if dot_pioreactor is not None else resolve_dot_pioreactor_path()
    source_path = str(CAMERA_STILLS_RELATIVE_DIR / unit / filename)
    metadata = CameraStillMetadata(
        unit=unit,
        experiment=experiment,
        captured_at=captured_at,
        image_id=image_id,
        filename=filename,
        resolution=resolution,
        capture_reason=capture_reason,
        source_path=source_path,
    )

    metadata_path = camera_still_metadata_path(unit, image_id, dot_pioreactor)
    metadata_bytes = json_encode(metadata)
    metadata_path.write_bytes(metadata_bytes)
    (unit_dir / LATEST_CAMERA_STILL_METADATA_FILENAME).write_bytes(metadata_bytes)

    apply_camera_still_retention(unit, retention_count=retention_count, dot_pioreactor=root)

    return metadata


def camera_still_metadata_path(unit: pt.Unit, image_id: str, dot_pioreactor: Path | None = None) -> Path:
    if not camera_storage_name_is_safe(image_id):
        raise ValueError(f"Unsafe camera image id: {image_id}")

    return camera_stills_unit_path(unit, dot_pioreactor) / f"{image_id}.json"


def latest_camera_still_metadata_path(unit: pt.Unit, dot_pioreactor: Path | None = None) -> Path:
    return camera_stills_unit_path(unit, dot_pioreactor) / LATEST_CAMERA_STILL_METADATA_FILENAME


def load_latest_camera_still_metadata(
    unit: pt.Unit, dot_pioreactor: Path | None = None
) -> CameraStillMetadata | None:
    metadata_path = latest_camera_still_metadata_path(unit, dot_pioreactor)

    if not metadata_path.exists():
        return None

    metadata = json_decode(metadata_path.read_bytes(), type=CameraStillMetadata)
    image_path = camera_still_image_path(metadata, dot_pioreactor)

    if not image_path.exists():
        return None

    return metadata


def camera_still_image_path(metadata: CameraStillMetadata, dot_pioreactor: Path | None = None) -> Path:
    root = dot_pioreactor if dot_pioreactor is not None else resolve_dot_pioreactor_path()
    return root / metadata.source_path


def list_camera_still_metadata(
    unit: pt.Unit, dot_pioreactor: Path | None = None
) -> list[CameraStillMetadata]:
    unit_dir = camera_stills_unit_path(unit, dot_pioreactor)

    if not unit_dir.exists():
        return []

    metadata: list[CameraStillMetadata] = []
    for metadata_path in unit_dir.glob("*.json"):
        if metadata_path.name == LATEST_CAMERA_STILL_METADATA_FILENAME:
            continue

        metadata.append(json_decode(metadata_path.read_bytes(), type=CameraStillMetadata))

    return sorted(metadata, key=lambda still: still.captured_at, reverse=True)


def apply_camera_still_retention(
    unit: pt.Unit,
    *,
    retention_count: int = DEFAULT_CAMERA_STILL_RETENTION_COUNT,
    dot_pioreactor: Path | None = None,
) -> None:
    if retention_count < 1:
        raise ValueError("Camera still retention count must be at least 1")

    retained = list_camera_still_metadata(unit, dot_pioreactor)[:retention_count]
    retained_ids = {still.image_id for still in retained}

    for still in list_camera_still_metadata(unit, dot_pioreactor)[retention_count:]:
        if still.image_id in retained_ids:
            continue

        image_path = camera_still_image_path(still, dot_pioreactor)
        if image_path.exists():
            image_path.unlink()

        metadata_path = camera_still_metadata_path(unit, still.image_id, dot_pioreactor)
        if metadata_path.exists():
            metadata_path.unlink()
