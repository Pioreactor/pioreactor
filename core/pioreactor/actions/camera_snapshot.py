# -*- coding: utf-8 -*-
import click
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.camera import CameraCaptureError
from pioreactor.camera import CameraStillMetadata
from pioreactor.camera import CameraUnavailableError
from pioreactor.camera import capture_camera_still
from pioreactor.utils import managed_lifecycle


def camera_snapshot(
    unit: pt.Unit | None = None,
    experiment: pt.Experiment | None = None,
) -> CameraStillMetadata:
    """Capture and store a still for the unit's assigned experiment."""
    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_assigned_experiment_name(unit)

    with managed_lifecycle(unit, experiment, "camera_snapshot"):
        return capture_camera_still(unit, experiment=experiment, capture_reason="manual")


@click.command(name="camera_snapshot")
def click_camera_snapshot() -> None:
    """Take a camera snapshot for the current experiment."""
    try:
        metadata = camera_snapshot()
    except (CameraUnavailableError, CameraCaptureError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    click.echo(f"Captured camera snapshot {metadata.image_id}.")
