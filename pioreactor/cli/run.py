# -*- coding: utf-8 -*-
# run.py
from __future__ import annotations

import click

from pioreactor import actions
from pioreactor import background_jobs as jobs
from pioreactor import plugin_management
from pioreactor.whoami import am_I_leader


@click.group(short_help="run a job")
def run() -> None:
    pass


# this runs on both leader and workers
run.add_command(jobs.monitor.click_monitor)


run.add_command(jobs.growth_rate_calculating.click_growth_rate_calculating)
run.add_command(jobs.stirring.click_stirring)
run.add_command(jobs.od_reading.click_od_reading)
run.add_command(jobs.dosing_control.click_dosing_control)
run.add_command(jobs.led_control.click_led_control)
run.add_command(jobs.temperature_control.click_temperature_control)

run.add_command(actions.led_intensity.click_led_intensity)
run.add_command(actions.pump.click_add_alt_media)
run.add_command(actions.pump.click_add_media)
run.add_command(actions.pump.click_remove_waste)
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
    run.add_command(jobs.mqtt_to_db_streaming.click_mqtt_to_db_streaming)
    run.add_command(jobs.watchdog.click_watchdog)
    run.add_command(actions.export_experiment_data.click_export_experiment_data)
    run.add_command(actions.backup_database.click_backup_database)
    run.add_command(actions.experiment_profile.click_experiment_profile)
