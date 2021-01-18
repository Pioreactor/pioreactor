# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring
> pio run od_reading --od-angle-channel 135,0
> pio log
"""
import logging
import click
from pioreactor.whoami import am_I_leader, am_I_active_worker, get_unit_name
from pioreactor.config import config
from pioreactor import background_jobs as jobs
from pioreactor import actions


logger = logging.getLogger(f"{get_unit_name()}-CLI")


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
    from sh import pkill

    try:
        # remove the _oldest_ one
        pkill("-f", f"run {process}")
    except Exception:
        pass


@pio.group(short_help="run a job")
def run():
    pass


# this runs on both leader and workers
run.add_command(jobs.monitor.click_monitor)

if am_I_active_worker():
    run.add_command(jobs.growth_rate_calculating.click_growth_rate_calculating)
    run.add_command(jobs.stirring.click_stirring)
    run.add_command(jobs.od_reading.click_od_reading)
    run.add_command(jobs.io_controlling.click_io_controlling)

    run.add_command(actions.add_alt_media.click_add_alt_media)
    run.add_command(actions.add_media.click_add_media)
    run.add_command(actions.remove_waste.click_remove_waste)
    run.add_command(actions.od_normalization.click_od_normalization)

if am_I_leader():
    run.add_command(jobs.log_aggregating.click_log_aggregating)
    run.add_command(jobs.mqtt_to_db_streaming.click_mqtt_to_db_streaming)
    run.add_command(jobs.time_series_aggregating.click_time_series_aggregating)
    run.add_command(jobs.watchdog.click_watchdog)

    run.add_command(actions.download_experiment_data.click_download_experiment_data)

    @pio.command(short_help="access the db CLI")
    def db():
        import os

        os.system(f"sqlite3 {config['storage']['observation_database']}")

    @pio.command(short_help="tail MQTT")
    def mqtt():
        import os

        os.system("mosquitto_sub -v -t 'pioreactor/#'")

    @pio.command(name="add-pioreactor", short_help="add new Pioreactor to cluster")
    @click.argument("new_name")
    def add_pioreactor(new_name):
        import subprocess
        import socket
        import time

        # check to make sure new_name isn't already on the network
        try:
            socket.gethostbyname(new_name)
        except socket.gaierror:
            pass
        else:
            raise IOError(f"Name {new_name} is already on the network. Try another name.")

        # check to make sure raspberrypi.local is on network
        raspberrypi_on_network = False
        checks, max_checks = 0, 60
        while not raspberrypi_on_network:
            checks += 1
            try:
                socket.gethostbyname("raspberrypi")
            except socket.gaierror:
                time.sleep(1)
                print("raspberrypi not found - checking again.")
                if checks >= max_checks:
                    raise IOError(
                        f"raspberrypi not found on network after {max_checks} seconds."
                    )
            else:
                raspberrypi_on_network = True

        subprocess.call(
            [
                "bash /home/pi/pioreactor/bash_scripts/add_new_worker_from_leader.sh %s"
                % new_name
            ],
            shell=True,
        )


if not am_I_leader() and not am_I_active_worker():
    logger.info(
        "Running `pio` on a non-active Pioreactor. Do you need to add this Pioreactor to `inventory` in `config.ini`?"
    )
