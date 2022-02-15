# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

import click

from pioreactor.actions.pump import pump
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name


def remove_waste(
    unit: str,
    experiment: str,
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[dict] = None,
    continuously: bool = False,
) -> float:
    """
    Parameters
    ------------
    unit: str
    experiment: str
    ml: float
        Amount of volume to pass, in mL
    duration: float
        Duration to run pump, in s
    calibration:
        specify a calibration for the dosing. Should be a dict
        with fields "duration_", "hz", "dc", and "bias_"
    continuously: bool
        Run pump continuously.
    source_of_event: str
        A human readable description of the source

    Returns
    -----------
    Amount of volume passed (approximate in some cases)

    """
    pump_name = "waste"
    return pump(
        unit,
        experiment,
        pump_name,
        ml,
        duration,
        source_of_event,
        calibration,
        continuously,
    )


@click.command(name="remove_waste")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option("--continuously", is_flag=True, help="continuously run until stopped.")
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - for logging",
)
def click_remove_waste(
    ml: Optional[float],
    duration: Optional[float],
    continuously: bool,
    source_of_event: Optional[str],
):
    """
    Remove waste/media from unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return remove_waste(
        ml=ml,
        duration=duration,
        continuously=continuously,
        source_of_event=source_of_event,
        unit=unit,
        experiment=experiment,
    )
