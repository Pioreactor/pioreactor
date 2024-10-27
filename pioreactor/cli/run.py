# -*- coding: utf-8 -*-
from __future__ import annotations

import click

from pioreactor import actions
from pioreactor import plugin_management
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


run.add_command(actions.led_intensity.click_led_intensity)
run.add_command(actions.pump.click_add_alt_media)
run.add_command(actions.pump.click_add_media)
run.add_command(actions.pump.click_remove_waste)
run.add_command(actions.pump.click_circulate_media)
run.add_command(actions.pump.click_circulate_alt_media)
run.add_command(actions.od_blank.click_od_blank)
run.add_command(actions.self_test.click_self_test)
run.add_command(actions.stirring_calibration.click_stirring_calibration)
run.add_command(actions.pump_calibration.click_pump_calibration)
run.add_command(actions.od_calibration.click_od_calibration)

# TODO: this only adds to `pio run` - what if users want to add a high level command? Examples?
for plugin in plugin_management.get_plugins().values():
    for possible_entry_point in dir(plugin.module):
        if possible_entry_point.startswith("click_"):
            run.add_command(getattr(plugin.module, possible_entry_point))

if am_I_leader():
    run.add_command(click_mqtt_to_db_streaming)
    run.add_command(actions.export_experiment_data.click_export_experiment_data)
    run.add_command(actions.backup_database.click_backup_database)
    run.add_command(actions.experiment_profile.click_experiment_profile)
