# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import ExitStack
from functools import wraps
from typing import Any
from typing import Iterable

import click
from click.core import ParameterSource
from pioreactor import plugin_management
from pioreactor.actions.leader.backup_database import click_backup_database
from pioreactor.actions.leader.experiment_profile import click_experiment_profile
from pioreactor.actions.leader.export_experiment_data import click_export_experiment_data
from pioreactor.actions.led_intensity import click_led_intensity
from pioreactor.actions.od_blank import click_od_blank
from pioreactor.actions.pump import click_add_alt_media
from pioreactor.actions.pump import click_add_media
from pioreactor.actions.pump import click_circulate_alt_media
from pioreactor.actions.pump import click_circulate_media
from pioreactor.actions.pump import click_remove_waste
from pioreactor.actions.pumps import click_pumps
from pioreactor.actions.self_test import click_self_test
from pioreactor.automations.dosing import *  # noqa: F403, F401
from pioreactor.automations.led import *  # noqa: F403, F401
from pioreactor.automations.temperature import *  # noqa: F403, F401
from pioreactor.background_jobs.dosing_automation import click_dosing_automation
from pioreactor.background_jobs.growth_rate_calculating import click_growth_rate_calculating
from pioreactor.background_jobs.leader.mqtt_to_db_streaming import click_mqtt_to_db_streaming
from pioreactor.background_jobs.led_automation import click_led_automation
from pioreactor.background_jobs.monitor import click_monitor
from pioreactor.background_jobs.od_reading import click_od_reading
from pioreactor.background_jobs.stirring import click_stirring
from pioreactor.background_jobs.temperature_automation import click_temperature_automation
from pioreactor.config import config
from pioreactor.config import temporary_config_changes
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import post_into
from pioreactor.utils.networking import resolve_to_address
from pioreactor.whoami import am_I_leader
from pioreactor.whoami import get_unit_name


@click.group(short_help="run a job", invoke_without_command=True)
@click.option(
    "--config-override",
    nargs=3,
    multiple=True,
    metavar="<section> <param> <value>",
    help="Temporarily override a config value",
)
@click.option(
    "-d",
    "--detach",
    is_flag=True,
    default=False,
    help="Submit the job to Huey and return immediately.",
)
@click.pass_context
def run(ctx, config_override: list[tuple[str, str, str | None]], detach: bool) -> None:
    """
    Run a job. Override the config with, example:

    pio run --config-override stirring.config,pwm_hz,100
    """
    ctx.ensure_object(dict)
    ctx.obj["config_override"] = config_override
    ctx.obj["detach"] = detach

    stack = ExitStack()
    stack.enter_context(temporary_config_changes(config, config_override))
    ctx.call_on_close(stack.close)

    # https://click.palletsprojects.com/en/8.1.x/commands/#group-invocation-without-command
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def detachable(command: click.Command) -> click.Command:
    original_callback = command.callback

    @wraps(original_callback)
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context()
        detach_requested = bool(ctx.find_object(dict).get("detach"))

        if not detach_requested:
            return original_callback(*args, **kwargs)

        payload = _build_detached_payload(ctx, command)
        _dispatch_detached_job(command.name, payload)
        return None

    command.callback = wrapper
    return command


def _build_detached_payload(ctx: click.Context, command: click.Command) -> dict[str, Any]:
    commandline_options: dict[str, Any] = {}

    for param in command.params:

        if param.name is None:
            continue
        value = ctx.params.get(param.name)

        if isinstance(param, click.Argument):
            raise click.UsageError("Detached runs do not support extra job arguments yet.")

        source = ctx.get_parameter_source(param.name)
        if source != ParameterSource.COMMANDLINE:
            continue

        commandline_options[param.name] = str(value)

    # this is only used in automations, since we pass through arbitrary context.
    commandline_options = commandline_options | {
        ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)
    }

    obj = ctx.find_object(dict) or {}
    config_override: Iterable[tuple[str, str, str | None]] = obj.get("config_override", ())

    return {
        "options": commandline_options,
        "args": [],
        "config_overrides": [list(item) for item in config_override],
    }


def _dispatch_detached_job(
    job_name: str,
    payload: dict[str, Any],
) -> None:
    address = resolve_to_address(
        get_unit_name()
    )  # can use localhost, but port might be different than default.
    try:
        response = post_into(address, f"/unit_api/jobs/run/job_name/{job_name}", json=payload)
        response.raise_for_status()
        result = response.json()
    except HTTPException as exc:
        raise click.ClickException(f"Unable to submit detached job ({address}): {exc}") from exc

    task_id = result["task_id"]
    result_path = result["result_url_path"]
    click.echo(f"Queued `{job_name}` as task {task_id}. Poll {result_path} for submission status.")


# this runs on both leader and workers
run.add_command(detachable(click_monitor))


run.add_command(detachable(click_growth_rate_calculating))
run.add_command(detachable(click_stirring))
run.add_command(detachable(click_od_reading))
run.add_command(detachable(click_dosing_automation))
run.add_command(detachable(click_led_automation))
run.add_command(detachable(click_temperature_automation))


run.add_command(detachable(click_led_intensity))
run.add_command(detachable(click_add_alt_media))
run.add_command(detachable(click_pumps))
run.add_command(detachable(click_add_media))
run.add_command(detachable(click_remove_waste))
run.add_command(detachable(click_circulate_media))
run.add_command(detachable(click_circulate_alt_media))
run.add_command(detachable(click_od_blank))
run.add_command(detachable(click_self_test))

for plugin in plugin_management.get_plugins().values():
    for possible_entry_point in dir(plugin.module):
        if possible_entry_point.startswith("click_"):
            # click.echo(
            #    f"The `click_` API is deprecated and will stop working in the future. You should update your plugins: {possible_entry_point}"
            # )
            run.add_command(detachable(getattr(plugin.module, possible_entry_point)))

if am_I_leader():
    run.add_command(detachable(click_mqtt_to_db_streaming))
    run.add_command(detachable(click_export_experiment_data))
    run.add_command(detachable(click_backup_database))
    run.add_command(detachable(click_experiment_profile))
