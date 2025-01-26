# -*- coding: utf-8 -*-
# pumps.py
# a higher-level CLI API than the `pio run add_*` api
from __future__ import annotations

from typing import Callable

import click

from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import remove_waste
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name

registered_pumps: dict[str, Callable[..., float]] = {
    "media": add_media,
    "alt_media": add_alt_media,
    "waste": remove_waste,
}


@click.command(
    name="pumps",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.pass_context
def click_pumps(ctx):
    """
    example: pio run pump --waste 2 --media 1 --waste 2
    """

    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    pump_script = [(ctx.args[i][2:], ctx.args[i + 1]) for i in range(0, len(ctx.args), 2)]

    for pump, volume in pump_script:
        volume = float(volume)
        pump = pump.rstrip("-").rstrip(
            "_"
        )  # why? users might be passing in the options via a key-value, and this way they can specify the same pump multiple times. Ex: experiment profiles.

        pump_func = registered_pumps.get(pump.replace("-", "_"))

        if pump_func:
            pump_func(ml=volume, unit=unit, experiment=experiment)
        else:
            raise ValueError(pump)
