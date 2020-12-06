# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring
> pio run od_reading --od-angle-channel 135,0
> pio log
"""
import click
from pioreactor.whoami import am_I_leader
from pioreactor.config import config


@click.group()
def pio():
    pass


@pio.command(name="logs", short_help="tail the logs")
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


@pio.group()
def run():
    pass


if am_I_leader():
    from pioreactor import background_jobs as bj
    from pioreactor import actions as a

    run.add_command(bj.log_aggregating.click_log_aggregating)
    run.add_command(bj.mqtt_to_db_streaming.click_mqtt_to_db_streaming)
    run.add_command(bj.time_series_aggregating.click_time_series_aggregating)

    run.add_command(a.download_experiment_data.click_download_experiment_data)


else:
    from pioreactor import background_jobs as bj
    from pioreactor import actions as a

    run.add_command(bj.growth_rate_calculating.click_growth_rate_calculating)
    run.add_command(bj.stirring.click_stirring)
    run.add_command(bj.od_reading.click_od_reading)
    run.add_command(bj.io_controlling.click_io_controlling)

    run.add_command(a.add_alt_media.click_add_alt_media)
    run.add_command(a.add_media.click_add_media)
    run.add_command(a.remove_waste.click_remove_waste)
    run.add_command(a.od_normalization.click_od_normalization)
