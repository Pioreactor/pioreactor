# -*- coding: utf-8 -*-
from contextlib import ExitStack

import click
from pioreactor import plugin_management
from pioreactor.cli.lazy_group import LazyGroup
from pioreactor.config import config
from pioreactor.config import temporary_config_changes
from pioreactor.whoami import am_I_leader

lazy_subcommands: dict[str, str] = {
    "monitor": "pioreactor.background_jobs.monitor.click_monitor",
    "growth_rate_calculating": "pioreactor.background_jobs.growth_rate_calculating.click_growth_rate_calculating",
    "stirring": "pioreactor.background_jobs.stirring.click_stirring",
    "od_reading": "pioreactor.background_jobs.od_reading.click_od_reading",
    "dosing_automation": "pioreactor.background_jobs.dosing_automation.click_dosing_automation",
    "led_automation": "pioreactor.background_jobs.led_automation.click_led_automation",
    "temperature_automation": "pioreactor.background_jobs.temperature_automation.click_temperature_automation",
    "led_intensity": "pioreactor.actions.led_intensity.click_led_intensity",
    "add_alt_media": "pioreactor.actions.pump.click_add_alt_media",
    "pumps": "pioreactor.actions.pumps.click_pumps",
    "add_media": "pioreactor.actions.pump.click_add_media",
    "remove_waste": "pioreactor.actions.pump.click_remove_waste",
    "circulate_media": "pioreactor.actions.pump.click_circulate_media",
    "circulate_alt_media": "pioreactor.actions.pump.click_circulate_alt_media",
    "od_blank": "pioreactor.actions.od_blank.click_od_blank",
    "self_test": "pioreactor.actions.self_test.click_self_test",
}

if am_I_leader():
    lazy_subcommands |= {
        "mqtt_to_db_streaming": "pioreactor.background_jobs.leader.mqtt_to_db_streaming.click_mqtt_to_db_streaming",
        "export_experiment_data": "pioreactor.actions.leader.export_experiment_data.click_export_experiment_data",
        "backup_database": "pioreactor.actions.leader.backup_database.click_backup_database",
        "experiment_profile": "pioreactor.actions.leader.experiment_profile.click_experiment_profile",
    }


class RunLazyGroup(LazyGroup):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._plugins_loaded = False

    def _load_plugins(self) -> None:
        if self._plugins_loaded:
            return
        for plugin in plugin_management.get_plugins().values():
            for possible_entry_point in dir(plugin.module):
                if possible_entry_point.startswith("click_"):
                    self.add_command(getattr(plugin.module, possible_entry_point))
        self._plugins_loaded = True

    def list_commands(self, ctx):
        self._load_plugins()
        return super().list_commands(ctx)

    def get_command(self, ctx, cmd_name):
        if cmd_name in {
            "dosing_automation",
            "led_automation",
            "temperature_automation",
        }:
            # These commands rely on plugin registration side-effects (automation subclasses).
            self._load_plugins()
        elif cmd_name not in self.lazy_subcommands and cmd_name not in self.commands:
            self._load_plugins()
        return super().get_command(ctx, cmd_name)


@click.group(
    short_help="run a job",
    invoke_without_command=True,
    cls=RunLazyGroup,
    lazy_subcommands=lazy_subcommands,
)
@click.option(
    "--config-override",
    nargs=3,
    multiple=True,
    metavar="<section> <param> <value>",
    help="Temporarily override a config value",
)
@click.pass_context
def run(ctx, config_override: list[tuple[str, str, str | None]]) -> None:
    """
    Run a job. Override the config with, example:

    pio run --config-override stirring.config,pwm_hz,100
    """
    stack = ExitStack()
    stack.enter_context(temporary_config_changes(config, config_override))
    ctx.call_on_close(stack.close)

    # https://click.palletsprojects.com/en/8.1.x/commands/#group-invocation-without-command
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
