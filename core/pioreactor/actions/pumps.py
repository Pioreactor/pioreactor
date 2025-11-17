# -*- coding: utf-8 -*-
# pumps.py
# a higher-level CLI API than the `pio run add_*` api
from __future__ import annotations

import time
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


def _validate_and_parse_pump_args_callback(ctx, param, value) -> list[tuple[str, float]]:
    """Validate and normalize pump/sleep pairs coming in as extra args.

    Accepts tokens like: ["--media", "2", "--sleep", "1", "--waste_", "0.5"].
    Returns a list of tuples: [(action, amount), ...] with action in registered_pumps or "sleep".
    """
    # When using ignore_unknown_options, unknown options land in ctx.args.
    # If Click didn't bind them to this argument, fall back to ctx.args.
    tokens = list(value) if value else list(ctx.args)

    if len(tokens) % 2 != 0:
        raise click.BadParameter("Arguments must be provided as pairs: <pump|sleep> <value>")

    valid_actions = set(registered_pumps.keys()) | {"sleep"}
    script: list[tuple[str, float]] = []

    for i in range(0, len(tokens), 2):
        raw_action = tokens[i]
        raw_amount = tokens[i + 1]

        # Normalize option-like actions (e.g., "--media", "--waste_", "--alt-media")
        action = raw_action.lstrip("-").rstrip("_").replace("-", "_")

        if action not in valid_actions:
            raise click.BadParameter(
                f"Unknown pump '{action}'. Choose from: {', '.join(sorted(valid_actions))}"
            )

        try:
            amount = float(raw_amount)
        except Exception:
            raise click.BadParameter(f"Value '{raw_amount}' for '{raw_action}' must be a number")

        script.append((action, amount))

    return script


@click.command(
    name="pumps",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("pump_script", nargs=-1, callback=_validate_and_parse_pump_args_callback)
@click.pass_context
def click_pumps(ctx, pump_script: list[tuple[str, float]]) -> None:
    """
    Run pumps in sequence. Accepts pairs of arguments where the first is the pump name (e.g., 'media', 'alt_media', 'waste') and the second is the volume in milliliters to pump.
    Also accepts a "sleep" command (with the second arg being the number of seconds to sleep).
    Example:

    pio run pumps --media 2 --waste 2 --media 1.5

    Use suffixed "_" to indicate the same pump multiple times for experiment profiles

    """

    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    for action, amount in pump_script:
        if action == "sleep":
            time.sleep(amount)
            continue

        pump_func = registered_pumps[action]
        pump_func(ml=amount, unit=unit, experiment=experiment)
