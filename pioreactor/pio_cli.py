# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring
> pio run od_reading --od-angle-channel 135,0
> pio log
"""
import click
from pioreactor.whoami import am_I_leader, am_I_active_worker
from pioreactor.config import config
from pioreactor import background_jobs as jobs
from pioreactor import actions


@click.group()
def pio():
    pass


@pio.command(name="logs", short_help="tail the log file")
def logs():
    """
    Tail the logs from /var/log/pioreactor.log to the terminal. CTRL-C to exit.
    """
    from sh import tail

    try:
        tail_sh = tail("-f", config["logging"]["log_file"], _iter=True)
        for line in tail_sh:
            print(line, end="")
    except KeyboardInterrupt:
        tail_sh.kill()


@pio.command(name="kill", short_help="kill job")
@click.argument("process")
def kill(process):
    """
    send SIGTERM signal to PROCESS
    """

    # TODO this fails for python
    from sh import kill, pgrep

    try:
        # remove the _oldest_ one
        kill(int(pgrep("-f", "-o", process)))
    except Exception:
        pass


@pio.group(short_help="run a job")
def run():
    pass


if am_I_active_worker():
    run.add_command(jobs.growth_rate_calculating.click_growth_rate_calculating)
    run.add_command(jobs.stirring.click_stirring)
    run.add_command(jobs.od_reading.click_od_reading)
    run.add_command(jobs.io_controlling.click_io_controlling)
    run.add_command(jobs.monitor.click_monitor)

    run.add_command(actions.add_alt_media.click_add_alt_media)
    run.add_command(actions.add_media.click_add_media)
    run.add_command(actions.remove_waste.click_remove_waste)
    run.add_command(actions.od_normalization.click_od_normalization)

if am_I_leader():
    run.add_command(jobs.log_aggregating.click_log_aggregating)
    run.add_command(jobs.mqtt_to_db_streaming.click_mqtt_to_db_streaming)
    run.add_command(jobs.time_series_aggregating.click_time_series_aggregating)

    run.add_command(actions.download_experiment_data.click_download_experiment_data)
