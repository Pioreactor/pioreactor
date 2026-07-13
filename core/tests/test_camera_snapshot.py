# -*- coding: utf-8 -*-
from contextlib import nullcontext
from datetime import datetime
from datetime import UTC
from unittest.mock import MagicMock

import pytest
from pioreactor.actions import camera_snapshot
from pioreactor.camera import CameraStillMetadata


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

    def capture(unit: str, *, experiment: str | None) -> CameraStillMetadata:
        captured["unit"] = unit
        captured["experiment"] = experiment
        return metadata

    monkeypatch.setattr(camera_snapshot, "capture_camera_still", capture)

    assert camera_snapshot.camera_snapshot() == metadata
    assert captured == {"unit": "unit-a", "experiment": "experiment-a"}
    lifecycle.assert_called_once_with("unit-a", "experiment-a", "camera_snapshot")
