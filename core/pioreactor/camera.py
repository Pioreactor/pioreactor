# -*- coding: utf-8 -*-
from __future__ import annotations

import fcntl
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime
from datetime import UTC
from pathlib import Path
from time import monotonic
from time import sleep
from typing import Annotated
from typing import cast
from typing import Iterator
from typing import Literal

from msgspec import DecodeError
from msgspec import Meta
from msgspec import Struct
from msgspec import to_builtins
from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode
from msgspec.structs import replace
from pioreactor import types as pt
from pioreactor.actions.led_intensity import is_led_channel_locked
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.paths import get_dot_pioreactor_path
from pioreactor.paths import get_run_pioreactor_path
from pioreactor.pubsub import subscribe
from pioreactor.states import JobState
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.job_manager import JobManager
from pioreactor.utils.sqlite_cache import cache as SqliteCache


CAMERA_STILLS_RELATIVE_DIR = Path("storage") / "camera_stills"
CAMERA_STILL_CONTENT_TYPE = "image/jpeg"
DEFAULT_CAMERA_STILL_RETENTION_COUNT = 500
CAMERA_STILLS_CACHE_NAME = "camera_stills"
CAMERA_SETTINGS_CACHE_NAME = "camera_settings"
AUTO_CAPTURE_ENABLED_KEY = "auto_capture_enabled"
RPICAM_CAPTURE_COMMANDS = ("rpicam-still", "libcamera-still")
CAMERA_WARMER_RUNTIME_DIR = get_run_pioreactor_path()
CAMERA_WARMER_STARTUP_GRACE_SECONDS = 1.0
CAMERA_WARMER_POLL_SECONDS = 0.01
CAMERA_OD_ALIGNMENT_GRACE_SECONDS = 5.0
RPICAM_AE_SETTLE_SECONDS = 1.0

type DefinitiveCameraDetectionStatus = Literal[
    "detected",
    "configured_camera_not_detected",
]
type CameraDetectionStatus = DefinitiveCameraDetectionStatus | Literal["unknown"]
type CameraCaptureReason = Literal["scheduled", "manual"]

camera_warmer_process: subprocess.Popen[bytes] | None = None
# Only definitive probe results are cached. Command failures and timeouts must remain retryable.
camera_hardware_detection_cache: dict[tuple[str, int], DefinitiveCameraDetectionStatus] = {}


class CameraStillMetadata(Struct, frozen=True):
    experiment: pt.Experiment | None
    captured_at: Annotated[datetime, Meta(tz=True)]
    image_id: str
    capture_reason: CameraCaptureReason = "scheduled"


class CameraUnavailableError(RuntimeError):
    pass


class CameraCaptureError(RuntimeError):
    pass


class CameraStillAlreadyExistsError(ValueError):
    pass


def camera_stills_root_path(dot_pioreactor: Path | None = None) -> Path:
    root = dot_pioreactor if dot_pioreactor is not None else get_dot_pioreactor_path()
    return root / CAMERA_STILLS_RELATIVE_DIR


def camera_focus_previews_root_path(dot_pioreactor: Path | None = None) -> Path:
    root = dot_pioreactor if dot_pioreactor is not None else get_dot_pioreactor_path()
    return root / "storage" / "camera_focus_previews"


def dev_camera_stills_path(dot_pioreactor: Path | None = None) -> Path:
    return camera_stills_root_path(dot_pioreactor) / "DEV_CAMERA_STILLS"


def camera_storage_name_is_safe(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_.-]+", value) is not None


def create_camera_image_id(captured_at: datetime | None = None) -> str:
    captured_at = captured_at or datetime.now(UTC)

    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)

    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def get_camera_capture_backend() -> Literal["rpicam", "v4l2"]:
    backend = config.get("camera", "capture_backend", fallback="rpicam")
    if backend not in {"rpicam", "v4l2"}:
        raise ValueError("camera.capture_backend must be either 'rpicam' or 'v4l2'")

    return cast(Literal["rpicam", "v4l2"], backend)


def get_camera_index() -> int:
    camera_index = config.getint("camera", "camera_index", fallback=0)
    if camera_index < 0:
        raise ValueError("camera.camera_index must be a non-negative integer")

    return camera_index


def get_camera_device_path() -> Path:
    device_path = config.get("camera", "device_path", fallback="/dev/video0").strip()
    if not device_path:
        raise ValueError("camera.device_path must not be empty")

    return Path(device_path)


def get_camera_ir_led_intensity() -> float:
    intensity = float(config.get("camera", "ir_led_intensity", fallback="25"))
    if not 0.0 <= intensity <= 100.0:
        raise ValueError("camera.ir_led_intensity must be between 0 and 100, inclusive")

    return intensity


def camera_should_be_kept_active() -> bool:
    return (
        config.getboolean("camera", "keep_camera_active", fallback=False)
        and get_camera_capture_backend() == "rpicam"
    )


def camera_is_enabled() -> bool:
    return config.getboolean("camera", "enabled", fallback=False)


def find_camera_capture_command(backend: Literal["rpicam", "v4l2"]) -> str | None:
    if backend == "v4l2":
        return shutil.which("fswebcam")

    for command in RPICAM_CAPTURE_COMMANDS:
        if resolved := shutil.which(command):
            return resolved

    return None


def get_rpicam_still_arguments(
    command: str,
    camera_index: int,
    dot_pioreactor: Path | None,
) -> list[str]:
    root = dot_pioreactor if dot_pioreactor is not None else get_dot_pioreactor_path()
    # Bound AE to 200 ms and 8x gain so clear samples brighten without holding shared IR for seconds.
    tuning_file = root / "camera" / "ov5647_noir_200ms.json"
    if not tuning_file.exists():
        raise CameraUnavailableError(f"Camera tuning file is missing: {tuning_file}")

    return [
        command,
        "--camera",
        str(camera_index),
        "--nopreview",
        "--tuning-file",
        tuning_file.as_posix(),
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
        "--metering",
        "spot",
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
        "75",
    ]


def camera_warmer_runtime_paths() -> tuple[Path, Path, Path, Path]:
    return (
        CAMERA_WARMER_RUNTIME_DIR / "camera-warmer.pid",
        CAMERA_WARMER_RUNTIME_DIR / "camera-warmer.jpg",
        CAMERA_WARMER_RUNTIME_DIR / "camera-warmer-latest.jpg",
        CAMERA_WARMER_RUNTIME_DIR / "camera-warmer-metadata.json",
    )


def camera_warmer_pid() -> int | None:
    pid_path, _, _, _ = camera_warmer_runtime_paths()
    if not pid_path.exists():
        return None

    try:
        pid = int(pid_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pid_path.unlink(missing_ok=True)
        return None

    command_line_path = Path("/proc") / str(pid) / "cmdline"
    if not command_line_path.exists():
        pid_path.unlink(missing_ok=True)
        return None

    try:
        command_line = command_line_path.read_bytes()
    except OSError:
        return None

    if b"rpicam-still" not in command_line:
        pid_path.unlink(missing_ok=True)
        return None

    return pid


def start_camera_warmer() -> bool:
    """Heat the camera chamber to reduce coverslip fogging at high headspace or culture temperatures."""
    global camera_warmer_process

    if not camera_should_be_kept_active():
        return False

    command = shutil.which("rpicam-still")
    if command is None:
        return False

    with camera_capture_lock():
        if camera_warmer_pid() is not None:
            return True

        pid_path, image_path, latest_path, metadata_path = camera_warmer_runtime_paths()
        CAMERA_WARMER_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        image_path.unlink(missing_ok=True)
        latest_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)

        try:
            process = subprocess.Popen(
                get_rpicam_still_arguments(command, get_camera_index(), None)
                + [
                    "--signal",
                    "--timeout",
                    "0",
                    "--latest",
                    latest_path.as_posix(),
                    "--metadata",
                    metadata_path.as_posix(),
                    "--metadata-format",
                    "json",
                    "-o",
                    image_path.as_posix(),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False

        sleep(CAMERA_WARMER_STARTUP_GRACE_SECONDS)
        if process.poll() is not None:
            return False

        pid_path.write_text(str(process.pid), encoding="utf-8")
        camera_warmer_process = process
        return True


def stop_camera_warmer() -> None:
    global camera_warmer_process

    with camera_capture_lock():
        pid = camera_warmer_pid()
        if pid is None:
            camera_warmer_process = None
            return

        try:
            os.kill(pid, signal.SIGUSR2)
        except ProcessLookupError:
            pass

        if camera_warmer_process is not None and camera_warmer_process.pid == pid:
            try:
                camera_warmer_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                pass

        camera_warmer_runtime_paths()[0].unlink(missing_ok=True)
        camera_warmer_process = None


def capture_camera_still_using_warmer(
    pid: int,
    timeout: float,
    capture_focus_score: bool,
) -> tuple[Path, int | None]:
    _, _, latest_path, metadata_path = camera_warmer_runtime_paths()
    latest_path.unlink(missing_ok=True)
    if capture_focus_score:
        metadata_path.unlink(missing_ok=True)

    if timeout <= RPICAM_AE_SETTLE_SECONDS:
        raise CameraCaptureError("The persistent camera process timed out before adjusting exposure.")

    deadline = monotonic() + timeout
    # The warmer meters darkness while IR is idle, so let it read illuminated frames before capture.
    sleep(RPICAM_AE_SETTLE_SECONDS)
    if monotonic() >= deadline:
        raise CameraCaptureError("The persistent camera process timed out while adjusting exposure.")

    try:
        os.kill(pid, signal.SIGUSR1)
    except ProcessLookupError as error:
        raise CameraCaptureError("The persistent camera process stopped before capture.") from error

    while monotonic() < deadline:
        if latest_path.exists() and not capture_focus_score:
            return latest_path, None

        if latest_path.exists() and metadata_path.exists():
            try:
                camera_metadata = json_decode(metadata_path.read_bytes())
            except DecodeError:
                sleep(CAMERA_WARMER_POLL_SECONDS)
                continue

            focus_score = camera_metadata.get("FocusFoM") if isinstance(camera_metadata, dict) else None
            return latest_path, focus_score if isinstance(focus_score, int) else None
        sleep(CAMERA_WARMER_POLL_SECONDS)

    raise CameraCaptureError("The persistent camera process timed out during capture.")


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
    capture_reason: CameraCaptureReason,
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
        capture_reason=capture_reason,
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


def get_rpicam_camera_detection_status(
    capture_command: str, camera_index: int, timeout: float = 3.0
) -> CameraDetectionStatus:
    try:
        result = subprocess.run(
            [capture_command, "--list-cameras"],
            capture_output=True,
            timeout=timeout,
            check=True,
        )
    except OSError as error:
        create_logger("camera", to_mqtt=False).debug(
            f"Unable to run `{capture_command} --list-cameras` while detecting camera index "
            f"{camera_index}: {error}."
        )
        return "unknown"
    except subprocess.CalledProcessError as error:
        create_logger("camera", to_mqtt=False).debug(
            f"`{capture_command} --list-cameras` exited with code {error.returncode} while detecting "
            f"camera index {camera_index}. stdout={error.stdout!r}, stderr={error.stderr!r}."
        )
        return "unknown"
    except subprocess.TimeoutExpired as error:
        create_logger("camera", to_mqtt=False).debug(
            f"`{capture_command} --list-cameras` timed out after {error.timeout} seconds while detecting "
            f"camera index {camera_index}. stdout={error.stdout!r}, stderr={error.stderr!r}."
        )
        return "unknown"

    output = (
        result.stdout.decode("utf-8", errors="replace")
        + "\n"
        + result.stderr.decode("utf-8", errors="replace")
    )

    if not re.search(rf"(?m)^\s*{camera_index}\s*:", output):
        create_logger("camera", to_mqtt=False).debug(
            f"`{capture_command} --list-cameras` did not report configured camera index {camera_index}. "
            f"stdout={result.stdout!r}, stderr={result.stderr!r}."
        )
        return "configured_camera_not_detected"

    return "detected"


def get_v4l2_camera_detection_status(device_path: Path) -> CameraDetectionStatus:
    if device_path.exists() and device_path.is_char_device():
        return "detected"
    return "configured_camera_not_detected"


def get_cached_rpicam_camera_detection_status(
    capture_command: str, camera_index: int
) -> CameraDetectionStatus:
    cache_key = (capture_command, camera_index)
    cached_status = camera_hardware_detection_cache.get(cache_key)
    if cached_status is not None:
        return cached_status

    detection_status = get_rpicam_camera_detection_status(capture_command, camera_index)
    if detection_status != "unknown":
        camera_hardware_detection_cache[cache_key] = detection_status

    return detection_status


def clear_camera_hardware_detection_cache() -> None:
    camera_hardware_detection_cache.clear()


def camera_auto_capture_is_enabled() -> bool:
    with local_persistent_storage(CAMERA_SETTINGS_CACHE_NAME) as storage:
        return storage.getboolean(AUTO_CAPTURE_ENABLED_KEY, fallback=True)


def set_camera_auto_capture_enabled(enabled: bool) -> bool:
    with local_persistent_storage(CAMERA_SETTINGS_CACHE_NAME) as storage:
        storage[AUTO_CAPTURE_ENABLED_KEY] = enabled

    return enabled


@contextmanager
def camera_capture_lock(dot_pioreactor: Path | None = None) -> Iterator[None]:
    """Serialize access to the physical camera across local processes."""
    lock_path = camera_stills_root_path(dot_pioreactor) / ".capture.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def get_camera_status(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None = None,
    dot_pioreactor: Path | None = None,
) -> dict[str, object]:
    backend = get_camera_capture_backend()
    camera_index = get_camera_index() if backend == "rpicam" else None
    device_path = get_camera_device_path() if backend == "v4l2" else None
    capture_command = find_camera_capture_command(backend)
    dev_stills_available = dev_camera_stills_are_available(dot_pioreactor)
    if dev_stills_available:
        detection_status: CameraDetectionStatus = "detected"
    elif capture_command is None:
        detection_status = "unknown"
    elif backend == "rpicam":
        assert camera_index is not None
        detection_status = get_cached_rpicam_camera_detection_status(capture_command, camera_index)
    else:
        assert device_path is not None
        detection_status = get_v4l2_camera_detection_status(device_path)
    latest_metadata = load_latest_camera_still_metadata(
        unit, experiment=experiment, dot_pioreactor=dot_pioreactor
    )
    if latest_metadata is None and dev_stills_available:
        latest_metadata = store_next_dev_camera_still(
            unit,
            experiment=experiment,
            capture_reason="scheduled",
            dot_pioreactor=dot_pioreactor,
        )

    return {
        "unit": unit,
        "detection_status": detection_status,
        "runtime_available": (capture_command is not None) or dev_stills_available,
        "capture_command": Path(capture_command).name if capture_command else None,
        "mock": dev_stills_available and capture_command is None,
        "latest_still": to_builtins(latest_metadata) if latest_metadata is not None else None,
        "auto_capture_enabled": camera_auto_capture_is_enabled(),
    }


@contextmanager
def camera_captured_image(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None,
    capture_focus_score: bool,
    timeout: float = 20.0,
    dot_pioreactor: Path | None = None,
) -> Iterator[tuple[Path, int | None]]:
    backend = get_camera_capture_backend()
    camera_index = get_camera_index() if backend == "rpicam" else None
    device_path = get_camera_device_path() if backend == "v4l2" else None
    command = find_camera_capture_command(backend)
    keep_camera_active = camera_should_be_kept_active()

    if command is None:
        source_paths = dev_camera_still_paths(dot_pioreactor)
        if source_paths:
            index = len(list_camera_still_metadata(unit, dot_pioreactor=dot_pioreactor)) % len(source_paths)
            with camera_capture_lock(dot_pioreactor):
                yield source_paths[index], None
            return

        raise CameraUnavailableError(f"No capture command is installed for camera backend '{backend}'.")

    with tempfile.NamedTemporaryFile(prefix="pioreactor-camera-", suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    metadata_path: Path | None = None
    try:
        if backend == "rpicam":
            assert camera_index is not None
            capture_arguments = get_rpicam_still_arguments(command, camera_index, dot_pioreactor) + [
                "--timeout",
                f"{RPICAM_AE_SETTLE_SECONDS:g}sec",
            ]
            if capture_focus_score:
                with tempfile.NamedTemporaryFile(
                    prefix="pioreactor-camera-", suffix=".json", delete=False
                ) as metadata_file:
                    metadata_path = Path(metadata_file.name)
                capture_arguments += [
                    "--metadata",
                    metadata_path.as_posix(),
                    "--metadata-format",
                    "json",
                ]
            capture_arguments += ["-o", tmp_path.as_posix()]
        else:
            assert device_path is not None
            capture_arguments = [
                command,
                "--device",
                device_path.as_posix(),
                "--no-banner",
                tmp_path.as_posix(),
            ]

        try:
            with camera_capture_lock(dot_pioreactor):
                ir_channel = cast(pt.LedChannel, config.get("leds_reverse", "IR"))

                with JobManager() as job_manager:
                    od_job_id = job_manager.get_running_job_id("od_reading")
                    od_job_info = job_manager.get_job_info(od_job_id) if od_job_id is not None else None
                    od_settings = (
                        {
                            setting: value
                            for setting, value, _created_at, _updated_at in job_manager.list_job_settings(
                                od_job_id
                            )
                        }
                        if od_job_id is not None
                        else {}
                    )

                od_interval = od_settings.get("interval")
                if od_settings.get("$state") == JobState.READY and od_interval is not None:
                    assert od_job_info is not None
                    od_readings_topic = f"pioreactor/{od_job_info[4]}/{od_job_info[2]}/od_reading/ods"
                    od_state_topic = f"pioreactor/{od_job_info[4]}/{od_job_info[2]}/od_reading/$state"
                    od_alignment_deadline = (
                        monotonic() + float(od_interval) + CAMERA_OD_ALIGNMENT_GRACE_SECONDS
                    )

                    # OD publishes `ods` only after turning IR off and releasing LED ownership.
                    # Starting on that fresh edge gives the camera the full quiet interval.
                    while True:
                        remaining_alignment_time = od_alignment_deadline - monotonic()
                        if remaining_alignment_time <= 0:
                            raise CameraCaptureError(
                                "Camera capture timed out waiting for a fresh OD reading."
                            )

                        od_event = subscribe(
                            [od_readings_topic, od_state_topic],
                            timeout=remaining_alignment_time,
                            allow_retained=False,
                            name="camera",
                        )
                        if od_event is not None:
                            if od_event.topic == od_readings_topic:
                                break
                            if od_event.payload.decode() != JobState.READY:
                                break
                            continue

                        with JobManager() as job_manager:
                            current_od_job_id = job_manager.get_running_job_id("od_reading")
                            current_od_state = (
                                job_manager.get_setting_from_running_job("od_reading", "$state")
                                if current_od_job_id == od_job_id
                                else None
                            )

                        if current_od_job_id != od_job_id or current_od_state != JobState.READY:
                            break

                        raise CameraCaptureError("Camera capture timed out waiting for a fresh OD reading.")

                capture_deadline = monotonic() + timeout

                # OD owns IR while taking a reading. Wait for that short window to finish before
                # starting the camera, but continue to let OD preempt a capture that is underway.
                while True:
                    if is_led_channel_locked(ir_channel):
                        if monotonic() >= capture_deadline:
                            raise CameraCaptureError(
                                "Camera capture timed out waiting for OD reading to release IR illumination."
                            )
                        sleep(CAMERA_WARMER_POLL_SECONDS)
                        continue

                    if not led_intensity(
                        {ir_channel: get_camera_ir_led_intensity()},
                        unit=unit,
                        experiment=experiment,
                        source_of_event="camera",
                        verbose=False,
                    ):
                        # OD may have acquired IR after the unlocked check above. Give it priority and retry.
                        if is_led_channel_locked(ir_channel):
                            continue
                        raise CameraCaptureError("Camera IR illumination could not be started.")
                    break

                try:
                    remaining_capture_time = capture_deadline - monotonic()
                    if remaining_capture_time <= 0:
                        raise CameraCaptureError("Camera capture timed out before taking a photo.")

                    focus_score: int | None = None
                    if keep_camera_active and (pid := camera_warmer_pid()) is not None:
                        captured_image_path, focus_score = capture_camera_still_using_warmer(
                            pid,
                            remaining_capture_time,
                            capture_focus_score,
                        )
                    else:
                        subprocess.run(
                            capture_arguments,
                            capture_output=True,
                            timeout=remaining_capture_time,
                            check=True,
                        )
                        captured_image_path = tmp_path
                        if metadata_path is not None and metadata_path.stat().st_size > 0:
                            try:
                                camera_metadata = json_decode(metadata_path.read_bytes())
                            except DecodeError:
                                camera_metadata = None
                            raw_focus_score = (
                                camera_metadata.get("FocusFoM") if isinstance(camera_metadata, dict) else None
                            )
                            focus_score = raw_focus_score if isinstance(raw_focus_score, int) else None
                finally:
                    # OD may have acquired IR while the command ran. A locked channel is OD's cleanup
                    # responsibility; otherwise camera restores the shared idle invariant of IR=0%.
                    if not is_led_channel_locked(ir_channel):
                        led_intensity(
                            {ir_channel: 0.0},
                            unit=unit,
                            experiment=experiment,
                            source_of_event="camera",
                            verbose=False,
                        )

                yield captured_image_path, focus_score
        except subprocess.CalledProcessError as error:
            stderr = error.stderr.decode("utf-8", errors="replace").strip()
            stdout = error.stdout.decode("utf-8", errors="replace").strip()
            message = stderr or stdout or f"{Path(command).name} exited with code {error.returncode}"
            raise CameraCaptureError(message) from error
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
        if metadata_path is not None:
            metadata_path.unlink(missing_ok=True)
        if keep_camera_active:
            start_camera_warmer()


def capture_camera_still(
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None,
    capture_reason: CameraCaptureReason,
    image_id: str | None = None,
    timeout: float = 20.0,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata:
    with camera_captured_image(
        unit,
        experiment=experiment,
        capture_focus_score=False,
        timeout=timeout,
        dot_pioreactor=dot_pioreactor,
    ) as (captured_image_path, _focus_score):
        return store_camera_still(
            captured_image_path,
            unit,
            experiment=experiment,
            capture_reason=capture_reason,
            image_id=image_id,
            dot_pioreactor=dot_pioreactor,
        )


def camera_focus_preview_path(session_id: str, dot_pioreactor: Path | None = None) -> Path:
    if not camera_storage_name_is_safe(session_id):
        raise ValueError(f"Unsafe camera focus session id: {session_id}")

    return camera_focus_previews_root_path(dot_pioreactor) / f"{session_id}.jpg"


def capture_camera_focus_preview(
    unit: pt.Unit,
    session_id: str,
    *,
    timeout: float = 20.0,
    dot_pioreactor: Path | None = None,
) -> tuple[Path, int | None]:
    preview_path = camera_focus_preview_path(session_id, dot_pioreactor)
    preview_path.parent.mkdir(parents=True, exist_ok=True)

    with camera_captured_image(
        unit,
        experiment="$experiment",
        capture_focus_score=True,
        timeout=timeout,
        dot_pioreactor=dot_pioreactor,
    ) as (captured_image_path, focus_score):
        with tempfile.NamedTemporaryFile(
            prefix=f"{session_id}-",
            suffix=".jpg",
            dir=preview_path.parent,
            delete=False,
        ) as temporary_preview_file:
            temporary_preview_path = Path(temporary_preview_file.name)

        try:
            shutil.copyfile(captured_image_path, temporary_preview_path)
            temporary_preview_path.chmod(0o664)  # Huey writes; www-data serves.
            temporary_preview_path.replace(preview_path)
        finally:
            temporary_preview_path.unlink(missing_ok=True)

    return preview_path, focus_score


def delete_camera_focus_preview(session_id: str, dot_pioreactor: Path | None = None) -> bool:
    preview_path = camera_focus_preview_path(session_id, dot_pioreactor)
    if not preview_path.exists():
        return False

    preview_path.unlink()
    return True


def store_camera_still(
    source_image_path: Path,
    unit: pt.Unit,
    *,
    experiment: pt.Experiment | None,
    capture_reason: CameraCaptureReason = "scheduled",
    captured_at: datetime | None = None,
    image_id: str | None = None,
    retention_count: int = DEFAULT_CAMERA_STILL_RETENTION_COUNT,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata:
    if not source_image_path.exists():
        raise FileNotFoundError(source_image_path)

    if retention_count < 2:
        raise ValueError("Camera still retention count must be at least 2")

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
    root = dot_pioreactor if dot_pioreactor is not None else get_dot_pioreactor_path()
    metadata = CameraStillMetadata(
        experiment=experiment,
        captured_at=captured_at,
        image_id=image_id,
        capture_reason=capture_reason,
    )

    if destination_image_path.exists():
        raise CameraStillAlreadyExistsError(f"Camera image name '{image_id}' already exists.")

    try:
        shutil.copyfile(source_image_path, destination_image_path)
        destination_image_path.chmod(0o664)  # Huey writes; www-data serves.
        with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
            initialize_camera_stills_metadata_storage(storage)
            storage[image_id] = json_encode(metadata)
    except (OSError, sqlite3.Error):
        destination_image_path.unlink(missing_ok=True)
        raise

    apply_camera_still_retention(
        unit,
        experiment=experiment,
        retention_count=retention_count,
        dot_pioreactor=root,
    )

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


def delete_camera_still(
    unit: pt.Unit,
    experiment: pt.Experiment,
    image_id: str,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata | None:
    metadata = load_camera_still_metadata(unit, experiment, image_id, dot_pioreactor)
    if metadata is None:
        return None

    image_path = camera_still_image_path(metadata, dot_pioreactor)
    if image_path.exists():
        image_path.unlink()

    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        storage.pop(image_id, None)

    return metadata


def rename_camera_still(
    unit: pt.Unit,
    experiment: pt.Experiment,
    image_id: str,
    new_image_id: str,
    dot_pioreactor: Path | None = None,
) -> CameraStillMetadata | None:
    if not camera_storage_name_is_safe(new_image_id):
        raise ValueError(f"Unsafe camera image id: {new_image_id}")

    metadata = load_camera_still_metadata(unit, experiment, image_id, dot_pioreactor)
    if metadata is None:
        return None

    if new_image_id == image_id:
        return metadata

    renamed_metadata = replace(metadata, image_id=new_image_id)
    source_image_path = camera_still_image_path(metadata, dot_pioreactor)
    destination_image_path = camera_still_image_path(renamed_metadata, dot_pioreactor)
    if destination_image_path.exists():
        raise CameraStillAlreadyExistsError(f"Camera image name '{new_image_id}' already exists.")

    source_image_path.rename(destination_image_path)
    try:
        with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
            storage.cursor.execute("BEGIN IMMEDIATE")
            try:
                storage[new_image_id] = json_encode(renamed_metadata)
                storage.pop(image_id)
                storage.conn.commit()
            except Exception:
                storage.conn.rollback()
                raise
    except Exception:
        destination_image_path.rename(source_image_path)
        raise

    return renamed_metadata


def delete_camera_stills_for_experiment(
    unit: pt.Unit,
    experiment: pt.Experiment,
    dot_pioreactor: Path | None = None,
) -> list[CameraStillMetadata]:
    """Delete every local camera still belonging to one experiment.

    Camera capture and cleanup share a lock so a completed capture cannot write a
    new still after experiment cleanup has enumerated the stored metadata.
    """
    if not camera_storage_name_is_safe(unit):
        raise ValueError(f"Unsafe camera unit name: {unit}")

    with camera_capture_lock(dot_pioreactor):
        with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
            initialize_camera_stills_metadata_storage(storage)
            metadata_rows = storage.cursor.execute(
                f"""
                SELECT value
                FROM {storage.table_name}
                WHERE json_extract(value, '$.experiment') = ?
                ORDER BY json_extract(value, '$.captured_at') ASC
                """,
                (experiment,),
            ).fetchall()
            metadata = [json_decode(value, type=CameraStillMetadata) for (value,) in metadata_rows]

            for still in metadata:
                image_path = camera_still_image_path(still, dot_pioreactor)
                if image_path.exists():
                    image_path.unlink()

            storage.cursor.execute(
                f"DELETE FROM {storage.table_name} WHERE json_extract(value, '$.experiment') = ?",
                (experiment,),
            )

    return metadata


def camera_still_image_path(metadata: CameraStillMetadata, dot_pioreactor: Path | None = None) -> Path:
    root = dot_pioreactor if dot_pioreactor is not None else get_dot_pioreactor_path()
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
    experiment: pt.Experiment | None,
    retention_count: int = DEFAULT_CAMERA_STILL_RETENTION_COUNT,
    dot_pioreactor: Path | None = None,
) -> None:
    """Retain a bounded temporal coreset of stills for one experiment.

    Stills are ordered from oldest to newest. Manual stills, and the first and newest stills, are
    invariants and are never eviction candidates. ``retention_count`` bounds scheduled stills only.
    When scheduled stills exceed that count, each scheduled interior still
    is assigned the product of its adjacent time gaps::

        (captured_at - previous.captured_at) * (next.captured_at - captured_at)

    Removing a still increases the sum of squared adjacent time gaps by twice this product, so
    evicting the smallest product is the locally least-damaging temporal thinning step. Repeating
    this after each capture progressively spreads the retained stills across the experiment instead
    of preserving only its newest tail.

    This is an online, irreversible approximation: an evicted image cannot be reconsidered as the
    experiment grows. ``experiment=None`` is treated as its own retention cohort.
    """
    if not camera_storage_name_is_safe(unit):
        raise ValueError(f"Unsafe camera unit name: {unit}")

    # Metadata written before capture_reason was added decodes as scheduled.
    count_query = f"""
        SELECT COUNT(*)
        FROM cache_{CAMERA_STILLS_CACHE_NAME}
        WHERE (
            json_extract(value, '$.capture_reason') = 'scheduled'
            OR json_type(value, '$.capture_reason') IS NULL
        )
          AND json_extract(value, '$.experiment')
    """
    params: tuple[pt.Experiment, ...]
    if experiment is None:
        count_query += " IS NULL"
        params = ()
    else:
        count_query += " = ?"
        params = (experiment,)

    with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
        initialize_camera_stills_metadata_storage(storage)
        scheduled_metadata_count = storage.cursor.execute(count_query, params).fetchone()[0]

    if scheduled_metadata_count <= retention_count:
        return

    if experiment is None:
        stills = [
            still
            for still in list_camera_still_metadata(
                unit,
                sort_order="asc",
                dot_pioreactor=dot_pioreactor,
            )
            if still.experiment is None
        ]
    else:
        stills = list_camera_still_metadata(
            unit,
            experiment=experiment,
            sort_order="asc",
            dot_pioreactor=dot_pioreactor,
        )

    scheduled_still_count = sum(still.capture_reason == "scheduled" for still in stills)
    while scheduled_still_count > retention_count:
        # Manual stills and the timeline endpoints are never candidates. Removing the scheduled
        # interior still with the smallest adjacent-gap product causes the smallest local increase
        # in squared time gaps.
        redundant_still_index = min(
            (index for index in range(1, len(stills) - 1) if stills[index].capture_reason == "scheduled"),
            key=lambda index: (
                (stills[index].captured_at - stills[index - 1].captured_at).total_seconds()
                * (stills[index + 1].captured_at - stills[index].captured_at).total_seconds(),
                stills[index].captured_at,
                stills[index].image_id,
            ),
        )
        still = stills.pop(redundant_still_index)
        scheduled_still_count -= 1

        image_path = camera_still_image_path(still, dot_pioreactor)
        if image_path.exists():
            image_path.unlink()

        with local_persistent_storage(CAMERA_STILLS_CACHE_NAME) as storage:
            storage.pop(still.image_id, None)
