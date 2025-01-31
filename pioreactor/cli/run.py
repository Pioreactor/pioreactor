# -*- coding: utf-8 -*-
from __future__ import annotations

import click

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
from pioreactor.whoami import am_I_leader

# required to "discover" automations


@click.group(short_help="run a job")
def run() -> None:
    pass


# this runs on both leader and workers
run.add_command(click_monitor)


run.add_command(click_growth_rate_calculating)
run.add_command(click_stirring)
run.add_command(click_od_reading)
run.add_command(click_dosing_automation)
run.add_command(click_led_automation)
run.add_command(click_temperature_automation)


run.add_command(click_led_intensity)
run.add_command(click_add_alt_media)
run.add_command(click_pumps)
run.add_command(click_add_media)
run.add_command(click_remove_waste)
run.add_command(click_circulate_media)
run.add_command(click_circulate_alt_media)
run.add_command(click_od_blank)
run.add_command(click_self_test)

for plugin in plugin_management.get_plugins().values():
    for possible_entry_point in dir(plugin.module):
        if possible_entry_point.startswith("click_"):
            # print(
            #    "The `click` API is deprecated and will stop working in the future. You should update your plugins."
            # )
            run.add_command(getattr(plugin.module, possible_entry_point))

if am_I_leader():
    run.add_command(click_mqtt_to_db_streaming)
    run.add_command(click_export_experiment_data)
    run.add_command(click_backup_database)
    run.add_command(click_experiment_profile)
