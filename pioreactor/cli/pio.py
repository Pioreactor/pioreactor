# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring
> pio run od_reading --od-angle-channel 135,0
> pio log
"""
import sys
import click
import pioreactor
from pioreactor.whoami import am_I_leader, am_I_active_worker, get_unit_name
from pioreactor.config import config
from pioreactor import background_jobs as jobs
from pioreactor import actions
from pioreactor.logging import create_logger


@click.group()
def pio():
    """
    Execute commands on this Pioreactor.
    See full documentation here: pioreactor.com/pages/Command-line-interface
    Report errors or feedback here: github.com/Pioreactor/pioreactor/issues
    """


@pio.command(name="logs", short_help="show recent logs")
def logs():
    """
    Tail and stream the logs the terminal. CTRL-C to exit.
    """
    from sh import tail
    from json import loads
    from pioreactor.pubsub import subscribe_and_callback
    from datetime import datetime

    def cb(msg):
        payload = loads(msg.payload.decode())
        click.echo(
            f"{datetime.utcnow().isoformat()} [{payload['task']}] {payload['level']} {payload['message']}"
        )

    click.echo(tail("-n", 100, config["logging"]["log_file"]))

    subscribe_and_callback(cb, "pioreactor/+/+/logs/+")

    while True:
        pass


@pio.command(name="kill", short_help="kill job(s)")
@click.argument("job", nargs=-1)
@click.option("--all", is_flag=True, help="kill all Pioreactor jobs running")
def kill(job, all):
    """
    stop a job by sending a SIGTERM to it.
    """

    from sh import pkill

    def safe_pkill(*args):
        try:
            pkill(*args)
            return 0
        except Exception:
            return 1

    if all:
        safe_pkill("-f", "pio run ")
    else:
        for j in job:
            result = safe_pkill("-f", f"pio run {j}")
            if not result:
                safe_pkill("-f", f"pio run-always {j}")


@pio.group(short_help="run a job")
def run():
    pass


@pio.group(name="run-always", short_help="run a permanent job")
def run_always():
    pass


@pio.command(name="list-plugins", short_help="list the installed plugins")
def list_plugins():

    for plugin in pioreactor.plugins.keys():
        click.echo(plugin)


@pio.command(name="version", short_help="print the version")
@click.option("--verbose", "-v", is_flag=True, help="show more system information")
def version(verbose):

    if verbose:
        import platform
        import board

        # TODO include HAT version and latest git shas
        click.echo(f"PioreactorApp: {pioreactor.__version__}")
        click.echo(f"OS:            {platform.platform()}")
        click.echo(f"Raspberry Pi:  {board.detector.get_device_model()}")
    else:
        click.echo(pioreactor.__version__)


@pio.command(name="update", short_help="update the Pioreactor software (app and ui)")
@click.option("--ui", is_flag=True, help="update the PioreactoUI to latest")
@click.option("--app", is_flag=True, help="update the PioreactoApp to latest")
def update(ui, app):
    import subprocess

    logger = create_logger("CLI")

    if (not app) and (not ui):
        click.echo("Nothing to do. Specify either --app or --ui.")

    if app:
        cd = "cd ~/pioreactor"
        gitp = "git pull origin master"
        setup = "sudo python3 setup.py install"
        command = " && ".join([cd, gitp, setup])
        p = subprocess.run(
            command,
            shell=True,
            universal_newlines=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if p.returncode == 0:
            logger.info("Updated PioreactorApp to latest version.")
        else:
            logger.error(p.stderr)

    if ui and am_I_leader():
        cd = "cd ~/pioreactorui/backend"
        gitp = "git pull origin master"
        setup = "pm2 restart ui"
        npm_install = "npm install"
        unedit_edited_files = "git checkout ."
        command = " && ".join([cd, gitp, setup, npm_install, unedit_edited_files])
        p = subprocess.run(
            command,
            shell=True,
            universal_newlines=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if p.returncode == 0:
            logger.info("Updated PioreactorUI to latest version.")
        else:
            logger.error(p.stderr)


# this runs on both leader and workers
run_always.add_command(jobs.monitor.click_monitor)

if am_I_active_worker():
    run.add_command(jobs.growth_rate_calculating.click_growth_rate_calculating)
    run.add_command(jobs.stirring.click_stirring)
    run.add_command(jobs.od_reading.click_od_reading)
    run.add_command(jobs.dosing_control.click_dosing_control)
    run.add_command(jobs.led_control.click_led_control)
    run.add_command(jobs.temperature_control.click_temperature_control)

    run.add_command(actions.add_alt_media.click_add_alt_media)
    run.add_command(actions.led_intensity.click_led_intensity)
    run.add_command(actions.add_media.click_add_media)
    run.add_command(actions.remove_waste.click_remove_waste)
    run.add_command(actions.od_normalization.click_od_normalization)
    run.add_command(actions.od_blank.click_od_blank)

    for plugin in pioreactor.plugins.values():
        for possible_entry_point in dir(plugin):
            if possible_entry_point.startswith("click_"):
                run.add_command(getattr(plugin, possible_entry_point))


if am_I_leader():
    run_always.add_command(jobs.mqtt_to_db_streaming.click_mqtt_to_db_streaming)
    run_always.add_command(jobs.watchdog.click_watchdog)

    run.add_command(actions.export_experiment_data.click_export_experiment_data)
    run.add_command(actions.backup_database.click_backup_database)

    @pio.command(short_help="access the db CLI")
    def db():
        import os

        os.system(f"sqlite3 {config['storage']['database']}")

    @pio.command(short_help="tail MQTT")
    @click.option("--topic", "-t", default="pioreactor/#")
    def mqtt(topic):
        import os

        os.system(f"""mosquitto_sub -v -t '{topic}' -F "%I %t %p" """)

    @pio.command(name="add-pioreactor", short_help="add a new Pioreactor to cluster")
    @click.argument("new_name")
    def add_pioreactor(new_name):
        """
        Add a new pioreactor to the cluster. new_name should be lowercase
        characters with only [a-z] and [0-9]
        """
        import socket
        import subprocess
        import re
        import time

        def is_allowable_hostname(hostname):
            return True if re.match(r"^[0-9a-zA-Z\-]+$", hostname) else False

        def is_host_on_network(hostname):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect((hostname, 22))
                s.close()
                return True
            except socket.error:
                return False

        # check to make sure new_name isn't already on the network
        if is_host_on_network(new_name):
            click.echo(
                f"Name {new_name} is already on the network. Try another name.", err=True
            )
            sys.exit(1)
        elif not is_allowable_hostname(new_name):
            click.echo(
                "New name should only contain numbers, -, and English alphabet: a-z.",
                err=True,
            )
            sys.exit(1)

        # check to make sure raspberrypi.local is on network
        raspberrypi_on_network = False
        checks, max_checks = 0, 20
        while not raspberrypi_on_network:
            checks += 1
            try:
                socket.gethostbyname("raspberrypi")
            except socket.gaierror:
                time.sleep(3)
                click.echo("`raspberrypi` not found on network- checking again.")
                if checks >= max_checks:
                    click.echo(
                        f"`raspberrypi` not found on network after {max_checks} seconds. Check that you provided the right Wifi credentials to the network.",
                        err=True,
                    )
                    sys.exit(1)
            else:
                raspberrypi_on_network = True

        res = subprocess.call(
            [
                "bash /home/pi/pioreactor/bash_scripts/add_new_worker_from_leader.sh %s"
                % new_name
            ],
            shell=True,
        )
        if res == 0:
            logger = create_logger("CLI")
            logger.info(f"New pioreactor {new_name} successfully added to cluster.")


if not am_I_leader() and not am_I_active_worker():
    logger = create_logger("CLI")
    logger.info(
        f"Running `pio` on a non-active Pioreactor. Do you need to change `{get_unit_name()}` in `network.inventory` section in `config.ini`?"
    )
