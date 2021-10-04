# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring
> pio run od_reading --od-angle-channel 135,0
> pio log
"""
import sys
import socket
from time import sleep

import click
import pioreactor
from pioreactor.whoami import (
    am_I_leader,
    am_I_active_worker,
    get_unit_name,
    UNIVERSAL_EXPERIMENT,
    get_rpi_machine,
)
from pioreactor.config import config, get_leader_hostname
from pioreactor import background_jobs as jobs
from pioreactor import actions
from pioreactor import plugin_management
from pioreactor.logging import create_logger
from pioreactor.pubsub import subscribe_and_callback, subscribe
from pioreactor.utils.gpio_helpers import temporarily_set_gpio_unavailable
import pioreactor.utils.networking as networking


@click.group()
def pio():
    """
    Execute commands on this Pioreactor.
    See full documentation here: https://pioreactor.com/pages/Command-line-interface
    Report errors or feedback here: https://github.com/Pioreactor/pioreactor/issues
    """


@pio.command(name="logs", short_help="show recent logs")
def logs():
    """
    Tail & stream the logs from this unit to the terminal. CTRL-C to exit.
    """
    from sh import tail
    from json import loads
    import time

    def cb(msg):
        payload = loads(msg.payload.decode())

        # time module is used below because it is the same that the logging module uses: https://docs.python.org/3/library/logging.html#logging.Formatter.formatTime
        click.echo(
            f"{time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime())} [{payload['task']}] {payload['level']} {payload['message']}"
        )

    click.echo(tail("-n", 100, config["logging"]["log_file"]))

    subscribe_and_callback(cb, f"pioreactor/{get_unit_name()}/+/logs/+")

    while True:
        time.sleep(0.1)


@pio.command(name="blink", short_help="blink LED")
def blink():
    import RPi.GPIO as GPIO

    GPIO.setmode(GPIO.BCM)

    from pioreactor.hardware_mappings import PCB_LED_PIN as LED_PIN

    def led_on():
        GPIO.output(LED_PIN, GPIO.HIGH)

    def led_off():
        GPIO.output(LED_PIN, GPIO.LOW)

    with temporarily_set_gpio_unavailable(LED_PIN):

        GPIO.setup(LED_PIN, GPIO.OUT)

        for _ in range(4):

            led_on()
            sleep(0.14)
            led_off()
            sleep(0.14)
            led_on()
            sleep(0.14)
            led_off()
            sleep(0.45)

        GPIO.cleanup(LED_PIN)


@pio.command(name="kill", short_help="kill job(s)")
@click.argument("job", nargs=-1)
@click.option("--all-jobs", is_flag=True, help="kill all Pioreactor jobs running")
def kill(job, all_jobs):
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

    if all_jobs:
        safe_pkill("-f", "pio run ")
    else:
        for j in job:
            safe_pkill("-f", f"pio run {j}")
            safe_pkill("-f", f"pio run-always {j}")


@pio.group(short_help="run a job")
def run():
    pass


@pio.group(name="run-always", short_help="run a long-lived job")
def run_always():
    pass


@pio.command(name="version", short_help="print the Pioreactor software version")
@click.option("--verbose", "-v", is_flag=True, help="show more system information")
def version(verbose):

    if verbose:
        import platform

        # TODO include HAT version and latest git shas
        click.echo(f"Pioreactor:             {pioreactor.__version__}")
        click.echo(f"Operating system:       {platform.platform()}")
        click.echo(f"Raspberry Pi:           {get_rpi_machine()}")
    else:
        click.echo(pioreactor.__version__)


@pio.command(name="view-cache", short_help="print out the contents of a cache")
@click.argument("cache")
def view_cache(cache):
    import os.path

    from pioreactor.utils import local_intermittent_storage, local_persistant_storage

    # is it a temp cache?
    if os.path.isfile(f"/tmp/{cache}.db"):
        with local_intermittent_storage(cache) as c:
            for key in c.keys():
                click.echo(f"{key.decode()} = {c[key].decode()}")

    elif os.path.isfile(f".pioreactor/local_storage/{cache}.db"):
        with local_persistant_storage(cache) as c:
            for key in c.keys():
                click.echo(f"{key.decode()} = {c[key].decode()}")
    else:
        click.echo(f"cache {cache} not found.")


@pio.command(name="update", short_help="update the Pioreactor software (app and/or UI)")
@click.option("--ui", is_flag=True, help="update the PioreactoUI to latest")
@click.option("--app", is_flag=True, help="update the PioreactoApp to latest")
def update(ui, app):
    import subprocess

    logger = create_logger(
        "update", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT
    )

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
        npm_install = "npm install"
        setup = "pm2 restart ui"
        unedit_edited_files = "git checkout ."  # TODO: why do I do this. Can I be more specific than `.`? This blocks edits to the contrib folder from sticking around.
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


pio.add_command(plugin_management.click_install_plugin)
pio.add_command(plugin_management.click_uninstall_plugin)
pio.add_command(plugin_management.click_list_plugins)

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
    run.add_command(actions.self_test.click_self_test)
    run.add_command(actions.stirring_calibration.click_stirring_calibration)

    for plugin in pioreactor.plugins.values():
        for possible_entry_point in dir(plugin.module):
            if possible_entry_point.startswith("click_"):
                run.add_command(getattr(plugin.module, possible_entry_point))


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
    @click.option(
        "--ip",
        help="instead of looking for raspberrypi.local on the network, look for the IP address.",
        default="",
    )
    def add_pioreactor(new_name, ip):
        """
        Add a new pioreactor to the cluster. new_name should be lowercase
        characters with only [a-z] and [0-9]
        """
        # TODO: move this to it's own file
        import socket
        import subprocess

        logger = create_logger(
            "add_pioreactor", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT
        )
        logger.info(f"Adding new pioreactor {new_name} to cluster.")

        # check to make sure new_name isn't already on the network
        if networking.is_hostname_on_network(new_name):
            logger.error(f"Name {new_name} is already on the network. Try another name.")
            click.echo(
                f"Name {new_name} is already on the network. Try another name.", err=True
            )
            sys.exit(1)
        elif not networking.is_allowable_hostname(new_name):
            click.echo(
                "New name should only contain numbers, -, and English alphabet: a-z.",
                err=True,
            )
            logger.error(
                "New name should only contain numbers, -, and English alphabet: a-z."
            )
            sys.exit(1)

        # check to make sure raspberrypi.local is on network
        raspberrypi_on_network = False
        checks, max_checks = 0, 20
        while not raspberrypi_on_network:
            checks += 1
            try:
                if ip:
                    socket.gethostbyaddr(ip)
                else:
                    socket.gethostbyname("raspberrypi")

            except socket.gaierror:
                machine_name = ip if ip else "raspberrypi"
                sleep(3)
                click.echo(f"`{machine_name}` not found on network - checking again.")
                if checks >= max_checks:
                    click.echo(
                        f"`{machine_name}` not found on network after {max_checks} seconds. Check that you provided the right WiFi credentials to the network, and that the Raspberry Pi is turned on.",
                        err=True,
                    )  # TODO - is this echo redundant?
                    logger.error(
                        f"`{machine_name}` not found on network after {max_checks} seconds. Check that you provided the right WiFi credentials to the network, and that the Raspberry Pi is turned on."
                    )
                    sys.exit(1)
            else:
                raspberrypi_on_network = True

        res = subprocess.call(
            [
                "bash /home/pi/pioreactor/bash_scripts/add_new_worker_from_leader.sh %s %s"
                % (new_name, ip)
            ],
            shell=True,
        )
        if res == 0:
            logger.info(f"New pioreactor {new_name} successfully added to cluster.")

    @pio.command(
        name="cluster-status", short_help="report information on the pioreactor cluster"
    )
    def cluster_status():

        click.secho(
            f"{'Unit name':20s} {'Is leader?':15s} {'IP address':20s} {'State':15s} {'Reachable?':10s}",
            bold=True,
        )
        for hostname, inventory_status in config["network.inventory"].items():
            if inventory_status == "0":
                continue

            # get ip
            if get_unit_name() == hostname:
                ip = networking.get_ip()
            else:
                try:
                    ip = socket.gethostbyname(hostname)
                except OSError:
                    ip = "Unknown"

            # get state
            result = subscribe(
                f"pioreactor/{hostname}/{UNIVERSAL_EXPERIMENT}/monitor/$state", timeout=1
            )
            if result:
                state = result.payload.decode()
            else:
                state = "Unknown"

            state = click.style(f"{state:15s}", fg="green" if state == "ready" else "red")

            # is reachable?
            reachable = networking.is_reachable(hostname)

            click.echo(
                f"{hostname:20s} {('Y' if hostname==get_leader_hostname() else 'N'):15s} {ip:20s} {state} {(  click.style('Y', fg='green') if reachable else click.style('N', fg='red') ):10s}"
            )


if not am_I_leader() and not am_I_active_worker():
    logger = create_logger("CLI", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
    logger.info(
        f"Running `pio` on a non-active Pioreactor. Do you need to change `{get_unit_name()}` in `network.inventory` section in `config.ini`?"
    )
