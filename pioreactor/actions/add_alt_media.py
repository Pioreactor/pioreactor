# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

import click

from pioreactor.actions.pump import pump
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name


def add_alt_media(
    unit: str,
    experiment: str,
    ml: Optional[float] = None,
    duration: Optional[float] = None,
    source_of_event: Optional[str] = None,
    calibration: Optional[dict] = None,
    continuously: bool = False,
) -> float:

    pump_name = "alt_media"
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


@click.command(name="add_alt_media")
@click.option("--ml", type=float)
@click.option("--duration", type=float)
@click.option(
    "--source-of-event",
    default="CLI",
    type=str,
    help="who is calling this function - data goes into database and MQTT",
)
def click_add_alt_media(ml, duration, source_of_event):
    """
    Add alternative media to unit
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    return add_alt_media(
        unit,
        experiment,
        ml,
        duration,
        source_of_event,
    )
