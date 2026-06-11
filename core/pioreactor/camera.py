# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from datetime import datetime
from datetime import UTC
from functools import cache
from pathlib import Path
from typing import Annotated
from typing import cast
from typing import Literal

from msgspec import Meta
from msgspec import Struct
from msgspec import to_builtins
from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode
from pioreactor import types as pt
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.sqlite_cache import cache as SqliteCache
from pioreactor.whoami import is_testing_env


CAMERA_STILLS_RELATIVE_DIR = Path("storage") / "camera_stills"
CAMERA_STILL_CONTENT_TYPE = "image/jpeg"
DEFAULT_CAMERA_STILL_RETENTION_COUNT = 200
CAMERA_STILLS_CACHE_NAME = "camera_stills"
CAMERA_CAPTURE_COMMANDS = ("rpicam-still", "libcamera-still")
DEV_CAMERA_STILLS_DIRNAME = "DEV_CAMERA_STILLS"

SAFE_CAMERA_STORAGE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class CameraStillMetadata(Struct, frozen=True):
    experiment: pt.Experiment | None
    captured_at: Annotated[datetime, Meta(tz=True)]
    image_id: str


class CameraUnavailableError(RuntimeError):
    pass


class CameraCaptureError(RuntimeError):
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


def dev_camera_stills_path(dot_pioreactor: Path | None = None) -> Path:
    return camera_stills_root_path(dot_pioreactor) / DEV_CAMERA_STILLS_DIRNAME


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
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata | None:
    source_paths = dev_camera_still_paths(dot_pioreactor)
    if not source_paths:
        return None

    index = len(list_camera_still_metadata(unit, dot_pioreactor=dot_pioreactor)) % len(source_paths)
    return store_camera_still(
        source_paths[index],
        unit,
        experiment=experiment,
        dot_pioreactor=dot_pioreactor,
    )


def initialize_camera_stills_metadata_storage(storage: SqliteCache) -> None:
    storage.cursor.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{storage.table_name}_captured_at
        ON {storage.table_name} (
            json_extract(value, '$.captured_at')
        )
        """
    )
    storage.cursor.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{storage.table_name}_experiment_captured_at
        ON {storage.table_name} (
            json_extract(value, '$.experiment'),
            json_extract(value, '$.captured_at')
        )
        """
    )


def query_camera_still_metadata(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None = None,
    limit: int | None = None,
    sort_order: Literal["asc", "desc"] = "desc",
    dot_pioreactor: Path | None = None,
) -> list[CameraStillMetadata]:
    if not camera_storage_name_is_safe(unit):
        raise ValueError(f"Unsafe camera unit name: {unit}")

    query = f"""
        SELECT value
        FROM cache_{CAMERA_STILLS_CACHE_NAME}
    """
    params: list[str | int] = []

    if experiment is not None:
        query += " WHERE json_extract(value, '$.experiment') = ?"
        params.append(experiment)

    order_direction = "ASC" if sort_order == "asc" else "DESC"
    query += f" ORDER BY json_extract(value, '$.captured_at') {order_direction}"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        initialize_camera_stills_metadata_storage(storage)
        metadata_rows = storage.cursor.execute(query, params).fetchall()

    metadata = [json_decode(value, type=CameraStillMetadata) for (value,) in metadata_rows]
    return [still for still in metadata if camera_still_image_path(still, dot_pioreactor).exists()]


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


@cache
def camera_hardware_is_detected_cached(capture_command: str) -> bool:
    return camera_hardware_is_detected(capture_command)


def clear_camera_hardware_detection_cache() -> None:
    camera_hardware_is_detected_cached.cache_clear()


def get_camera_status(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None = None,
    dot_pioreactor: Path | None = None,
) -> dict[str, object]:
    capture_command = find_camera_capture_command()
    dev_stills_available = dev_camera_stills_are_available(dot_pioreactor)
    camera_detected = (
        camera_hardware_is_detected_cached(capture_command) if capture_command is not None else False
    ) or dev_stills_available
    latest_metadata = load_latest_camera_still_metadata(
        unit, experiment=experiment, dot_pioreactor=dot_pioreactor
    )
    if latest_metadata is None and dev_stills_available:
        latest_metadata = store_next_dev_camera_still(
            unit,
            experiment=experiment,
            dot_pioreactor=dot_pioreactor,
        )

    return {
        "unit": unit,
        "available": camera_detected,
        "runtime_available": (capture_command is not None) or dev_stills_available,
        "capture_available": camera_detected,
        "capture_command": Path(capture_command).name if capture_command else None,
        "mock": dev_stills_available and capture_command is None,
        "latest_still": to_builtins(latest_metadata) if latest_metadata is not None else None,
    }


def capture_camera_still(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None,
    timeout: float = 20.0,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata:
    command = find_camera_capture_command()

    if command is None:
        dev_still = store_next_dev_camera_still(
            unit,
            experiment=experiment,
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
            dot_pioreactor=dot_pioreactor,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def store_camera_still(
    source_image_path: Path,
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None,
    captured_at: datetime | None = None,
    image_id: str | None = None,
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

    if not camera_storage_name_is_safe(unit):
        raise ValueError(f"Unsafe camera unit name: {unit}")

    stills_root = camera_stills_root_path(dot_pioreactor)
    stills_root.mkdir(parents=True, exist_ok=True)

    filename = camera_still_filename(image_id)
    destination_image_path = stills_root / filename
    shutil.copyfile(source_image_path, destination_image_path)

    root = dot_pioreactor if dot_pioreactor is not None else resolve_dot_pioreactor_path()
    metadata = CameraStillMetadata(
        experiment=experiment,
        captured_at=captured_at,
        image_id=image_id,
    )

    metadata_bytes = json_encode(metadata)
    try:
        with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
            initialize_camera_stills_metadata_storage(storage)
            storage[image_id] = metadata_bytes
    except sqlite3.Error:
        if destination_image_path.exists():
            destination_image_path.unlink()
        raise

    apply_camera_still_retention(unit, retention_count=retention_count, dot_pioreactor=root)

    return metadata


def load_latest_camera_still_metadata(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None = None,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata | None:
    metadata = query_camera_still_metadata(
        unit,
        experiment=experiment,
        limit=1,
        dot_pioreactor=dot_pioreactor,
    )
    return metadata[0] if metadata else None


def load_camera_still_metadata(
    unit: pt.Unit,
    experiment: pt.Experiment,
    image_id: str,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata | None:
    if not camera_storage_name_is_safe(unit):
        raise ValueError(f"Unsafe camera unit name: {unit}")

    if not camera_storage_name_is_safe(image_id):
        raise ValueError(f"Unsafe camera image id: {image_id}")

    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        raw_metadata = storage.get(image_id)

    if raw_metadata is None:
        return None

    metadata = json_decode(cast(str | bytes | bytearray, raw_metadata), type=CameraStillMetadata)
    if metadata.experiment != experiment:
        return None

    if not camera_still_image_path(metadata, dot_pioreactor).exists():
        return None

    return metadata


def camera_still_image_path(metadata: CameraStillMetadata, dot_pioreactor: Path | None = None) -> Path:
    root = dot_pioreactor if dot_pioreactor is not None else resolve_dot_pioreactor_path()
    return root / CAMERA_STILLS_RELATIVE_DIR / camera_still_filename(metadata.image_id)


def camera_still_filename(image_id: str) -> str:
    return f"{image_id}.jpg"


def list_camera_still_metadata(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None = None,
    limit: int | None = None,
    sort_order: Literal["asc", "desc"] = "desc",
    dot_pioreactor: Path | None = None,
) -> list[CameraStillMetadata]:
    return query_camera_still_metadata(
        unit,
        experiment=experiment,
        limit=limit,
        sort_order=sort_order,
        dot_pioreactor=dot_pioreactor,
    )


def apply_camera_still_retention(
    unit: pt.Unit,
    *,
    retention_count: int = DEFAULT_CAMERA_STILL_RETENTION_COUNT,
    dot_pioreactor: Path | None = None,
) -> None:
    if retention_count < 1:
        raise ValueError("Camera still retention count must be at least 1")

    retained = list_camera_still_metadata(unit, dot_pioreactor=dot_pioreactor)[:retention_count]
    retained_ids = {still.image_id for still in retained}

    for still in list_camera_still_metadata(unit, dot_pioreactor=dot_pioreactor)[retention_count:]:
        if still.image_id in retained_ids:
            continue

        image_path = camera_still_image_path(still, dot_pioreactor)
        if image_path.exists():
            image_path.unlink()

        with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
            storage.pop(still.image_id, None)
