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


FOCUS_SCORE_TOLERANCE = 0.05


def focus_guidance_from_scores(focus_scores: list[int | None]) -> tuple[str, str]:
    """Return guidance from the full sequence of focus measurements."""
    if not focus_scores or focus_scores[-1] is None:
        return (
            "unavailable",
            "Automatic focus guidance isn't available for this camera. Compare snapshots visually.",
        )

    valid_focus_scores = [score for score in focus_scores if score is not None]
    if len(valid_focus_scores) == 1:
        return "initial", "Adjust the focus slightly, then take another snapshot."

    comparison_focus_score = valid_focus_scores[0]
    best_focus_score = valid_focus_scores[0]
    guidance_status = "initial"
    guidance = "Adjust the focus slightly, then take another snapshot."

    for index, focus_score in enumerate(valid_focus_scores[1:], start=1):
        # Wait for three usable captures before suggesting that the user can finish.
        if (
            index >= 2
            and focus_score <= best_focus_score
            and focus_score >= best_focus_score * (1 - FOCUS_SCORE_TOLERANCE)
        ):
            guidance_status = "sharpest"
            guidance = "You're in the sharpest range found. You can finish focusing."
            comparison_focus_score = focus_score
        elif focus_score > comparison_focus_score * (1 + FOCUS_SCORE_TOLERANCE):
            guidance_status = "sharper"
            guidance = "Sharper — keep turning in the same direction."
            comparison_focus_score = focus_score
        elif focus_score < comparison_focus_score * (1 - FOCUS_SCORE_TOLERANCE):
            guidance_status = "blurrier"
            guidance = "Blurrier — turn back slightly."
            comparison_focus_score = focus_score
        else:
            # Keep the comparison point fixed so individually small changes accumulate.
            guidance_status = "same"
            guidance = "No clear change yet — keep turning a little in the same direction."

        best_focus_score = max(best_focus_score, focus_score)

    return guidance_status, guidance


def start_manual_focus_session(target_device: Literal["camera"]) -> CalibrationSession:
    session_id = str(uuid.uuid4())
    now = utc_iso_timestamp()
    return CalibrationSession(
        session_id=session_id,
        protocol_name=ManualCameraFocusProtocol.protocol_name,
        target_device=target_device,
        status="in_progress",
        step_id="take_snapshot",
        data={
            "unit": get_unit_name(),
            "snapshot_count": 0,
            "focus_scores": [],
        },
        created_at=now,
        updated_at=now,
    )


def capture_focus_snapshot(ctx: SessionContext) -> None:
    if ctx.mode != "ui" or ctx.executor is None:
        raise ValueError("Manual camera focus is only available in the Pioreactor UI.")

    result = ctx.executor(
        "camera_focus_capture",
        {
            "unit": ctx.data["unit"],
            "session_id": ctx.session.session_id,
        },
    )
    focus_score = result.get("focus_score")
    if not isinstance(focus_score, int):
        focus_score = None

    ctx.data["focus_scores"].append(focus_score)
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
        step.metadata = {
            "dialog": {
                "max_width": "md",
                "height": "min(90vh, 860px)",
            },
            "primary_action_label": "Take snapshot",
        }
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        capture_focus_snapshot(ctx)
        return FocusCamera()


class FocusCamera(SessionStep):
    step_id = "focus_camera"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        unit = str(ctx.data["unit"])
        snapshot_count = int(ctx.data["snapshot_count"])

        guidance_status, guidance = focus_guidance_from_scores(ctx.data["focus_scores"])

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
                "max_height": 300,
                "aspect_ratio": "4 / 3",
            },
            "actions": [
                {
                    "label": "Take another snapshot",
                    "inputs": {"action": "retake"},
                    "updates_image": True,
                },
            ],
            "dialog": {
                "max_width": "md",
                "height": "min(90vh, 860px)",
            },
            "guidance": {
                "title": "Focus guidance",
                "status": guidance_status,
                "message": guidance,
            },
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
