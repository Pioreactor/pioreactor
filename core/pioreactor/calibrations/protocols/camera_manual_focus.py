# -*- coding: utf-8 -*-
import uuid
from typing import ClassVar
from typing import Literal
from urllib.parse import quote

import click
from pioreactor import structs
from pioreactor.calibrations.registry import CalibrationProtocol
from pioreactor.calibrations.registry import SessionCleanupExecutor
from pioreactor.calibrations.session_flow import CalibrationComplete
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionStep
from pioreactor.calibrations.session_flow import StepRegistry
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.whoami import get_unit_name


def start_manual_focus_session(target_device: Literal["camera"]) -> CalibrationSession:
    session_id = str(uuid.uuid4())
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id=session_id,
        protocol_name=ManualCameraFocusProtocol.protocol_name,
        target_device=target_device,
        status="in_progress",
        step_id="take_snapshot",
        data={"unit": get_unit_name(), "snapshot_count": 0},
        created_at=now,
        updated_at=now,
    )


def capture_focus_snapshot(ctx: SessionContext) -> None:
    if ctx.mode != "ui" or ctx.executor is None:
        raise ValueError("Manual camera focus is only available in the Pioreactor UI.")

    ctx.executor(
        "camera_focus_capture",
        {
            "unit": ctx.data["unit"],
            "session_id": ctx.session.session_id,
        },
    )
    ctx.data["snapshot_count"] = int(ctx.data.get("snapshot_count", 0)) + 1


def cleanup_focus_snapshots(
    session: CalibrationSession,
    executor: SessionCleanupExecutor | None,
) -> None:
    if executor is None:
        return

    executor(
        "camera_focus_cleanup",
        {
            "unit": session.data["unit"],
            "session_id": session.session_id,
        },
    )


class TakeSnapshot(SessionStep):
    step_id = "take_snapshot"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        step = steps.action(
            "Prepare the focus target",
            "Point the camera at a detailed object near the intended vial position, then press Take snapshot "
            "to take a snapshot.",
        )
        step.metadata = {"primary_action_label": "Take snapshot"}
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        capture_focus_snapshot(ctx)
        return FocusCamera()


class FocusCamera(SessionStep):
    step_id = "focus_camera"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        unit = str(ctx.data["unit"])
        snapshot_count = int(ctx.data["snapshot_count"])
        step = steps.info(
            "Adjust the camera focus",
            "Turn the camera's focus control until fine details look sharp. Take another snapshot to "
            "check the adjustment, or press Focus is complete when the image is sharp.",
        )
        step.metadata = {
            "image": {
                "src": (
                    f"/api/workers/{quote(unit, safe='')}/camera/focus_sessions/"
                    f"{quote(ctx.session.session_id, safe='')}/preview.jpg?v={snapshot_count}"
                ),
                "alt": f"Camera focus snapshot from {unit}.",
                "caption": f"Focus snapshot {snapshot_count}",
            },
            "actions": [
                {"label": "Take another snapshot", "inputs": {"action": "retake"}},
            ],
            "primary_action_label": "Focus is complete",
        }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        if ctx.inputs.raw and ctx.inputs.raw.get("action") == "retake":
            capture_focus_snapshot(ctx)
            return FocusCamera()

        cleanup_focus_snapshots(ctx.session, ctx.executor)
        ctx.complete({"title": "Camera focus complete"})
        return CalibrationComplete()


_MANUAL_FOCUS_STEPS: StepRegistry = {
    TakeSnapshot.step_id: TakeSnapshot,
    FocusCamera.step_id: FocusCamera,
}


class ManualCameraFocusProtocol(CalibrationProtocol[Literal["camera"]]):
    target_device = "camera"
    protocol_name = "manual_focus"
    title = "Manual camera focus"
    description = "Capture still images while manually adjusting the camera's focus."
    requirements = (
        "Camera connected",
        "Detailed focus target near the intended vial position",
        "Physical access to the camera focus control",
    )
    step_registry: ClassVar[StepRegistry] = _MANUAL_FOCUS_STEPS

    @classmethod
    def start_session(cls, target_device: Literal["camera"]) -> CalibrationSession:
        return start_manual_focus_session(target_device)

    @classmethod
    def on_session_abort(
        cls,
        session: CalibrationSession,
        executor: SessionCleanupExecutor | None = None,
    ) -> None:
        cleanup_focus_snapshots(session, executor)

    def run(self, target_device: Literal["camera"]) -> structs.CalibrationBase:
        raise click.UsageError("Manual camera focus is only available in the Pioreactor UI.")
