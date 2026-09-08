# -*- coding: utf-8 -*-
from contextlib import nullcontext
from datetime import datetime
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from pioreactor import camera
from pioreactor.actions import camera_snapshot
from pioreactor.camera import CameraStillMetadata
from pioreactor.config import temporary_config_change


def test_camera_snapshot_uses_current_unit_and_experiment(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = CameraStillMetadata(
        experiment="experiment-a",
        captured_at=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        image_id="image-a",
    )
    captured: dict[str, str | None] = {}
    lifecycle = MagicMock(return_value=nullcontext())

    monkeypatch.setattr(camera_snapshot.whoami, "get_unit_name", lambda: "unit-a")
    monkeypatch.setattr(
        camera_snapshot.whoami,
        "get_assigned_experiment_name",
        lambda unit: "experiment-a",
    )
    monkeypatch.setattr(camera_snapshot, "managed_lifecycle", lifecycle)

    def capture(
        unit: str,
        *,
        experiment: str | None,
        capture_reason: str,
        image_id: str | None,
        capture_profile: Path | None,
    ) -> CameraStillMetadata:
        captured["unit"] = unit
        captured["experiment"] = experiment
        captured["capture_reason"] = capture_reason
        captured["image_id"] = image_id
        return metadata

    monkeypatch.setattr(camera_snapshot, "capture_camera_still", capture)

    assert camera_snapshot.camera_snapshot() == metadata
    assert captured == {
        "unit": "unit-a",
        "experiment": "experiment-a",
        "capture_reason": "manual",
        "image_id": None,
    }
    lifecycle.assert_called_once_with("unit-a", "experiment-a", "camera_snapshot")


@pytest.mark.parametrize(
    ("name", "expected_image_id"),
    [("inoculation", "inoculation"), ("run.05", "run.05"), ("run.05.jpg", "run.05")],
)
def test_camera_snapshot_passes_name_as_image_id(
    monkeypatch: pytest.MonkeyPatch, name: str, expected_image_id: str
) -> None:
    metadata = CameraStillMetadata(
        experiment="experiment-a",
        captured_at=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        image_id=expected_image_id,
    )
    captured: dict[str, str | None] = {}

    monkeypatch.setattr(camera_snapshot, "managed_lifecycle", lambda *_args: nullcontext())

    def capture(
        unit: str,
        *,
        experiment: str | None,
        capture_reason: str,
        image_id: str | None,
        capture_profile: Path | None,
    ) -> CameraStillMetadata:
        captured["image_id"] = image_id
        return metadata

    monkeypatch.setattr(camera_snapshot, "capture_camera_still", capture)

    assert camera_snapshot.camera_snapshot("unit-a", "experiment-a", name=name) == metadata
    assert captured["image_id"] == expected_image_id


def test_camera_snapshot_rejects_unsafe_name_before_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    capture = MagicMock()
    monkeypatch.setattr(camera_snapshot, "capture_camera_still", capture)

    with pytest.raises(ValueError, match="Unsafe camera image name"):
        camera_snapshot.camera_snapshot("unit-a", "experiment-a", name="../inoculation")

    capture.assert_not_called()


@pytest.mark.parametrize("warmer_running", [False, True])
def test_camera_snapshot_cli_capture_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, warmer_running: bool
) -> None:
    profile = tmp_path / "custom.conf"
    profile.write_text("width=640\n", encoding="utf-8")
    metadata = CameraStillMetadata(
        experiment="experiment-a",
        captured_at=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        image_id="image-a",
    )
    monkeypatch.setattr(camera_snapshot.whoami, "get_unit_name", lambda: "unit-a")
    monkeypatch.setattr(camera_snapshot.whoami, "get_assigned_experiment_name", lambda _unit: "experiment-a")
    monkeypatch.setattr(camera_snapshot, "managed_lifecycle", lambda *_args: nullcontext())
    monkeypatch.setattr(camera, "find_camera_capture_command", lambda _backend: "/usr/bin/rpicam-still")
    monkeypatch.setattr(camera, "camera_warmer_pid", lambda: 123 if warmer_running else None)
    run = MagicMock()
    store = MagicMock(return_value=metadata)
    start_warmer = MagicMock()
    monkeypatch.setattr(camera.subprocess, "run", run)
    monkeypatch.setattr(camera, "store_camera_still", store)
    monkeypatch.setattr(camera, "start_camera_warmer", start_warmer)

    with temporary_config_change(
        camera.config, "camera", "capture_backend", "rpicam"
    ), temporary_config_change(camera.config, "camera", "use_ir_led", "0"), temporary_config_change(
        camera.config, "camera", "keep_camera_active", "1"
    ):
        result = CliRunner().invoke(camera_snapshot.click_camera_snapshot, ["--config", str(profile)])

    if warmer_running:
        assert result.exit_code == 1
        assert "Stop the camera warmer before using --config" in result.output
        run.assert_not_called()
        store.assert_not_called()
    else:
        assert result.exit_code == 0, result.output
        arguments = run.call_args.args[0]
        assert arguments[arguments.index("--config") + 1] == str(profile)
        assert run.call_args.kwargs["cwd"] == tmp_path
        store.assert_called_once()
    start_warmer.assert_not_called()
