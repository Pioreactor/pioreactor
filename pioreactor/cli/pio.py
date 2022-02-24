# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring
> pio run od_reading --od-angle-channel 135,0
> pio log
"""
from __future__ import annotations

import socket
import sys
from time import sleep
from typing import Optional

import click

import pioreactor
import pioreactor.utils.networking as networking
from pioreactor import actions
from pioreactor import background_jobs as jobs
from pioreactor import plugin_management
from pioreactor.config import config
from pioreactor.config import get_leader_hostname
from pioreactor.logging import create_logger
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.gpio_helpers import temporarily_set_gpio_unavailable
from pioreactor.whoami import am_I_active_worker
from pioreactor.whoami import am_I_leader
from pioreactor.whoami import get_rpi_machine
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


@click.group()
def pio() -> None:
    """
    Execute commands on this Pioreactor.
    See full documentation here: https://docs.pioreactor.com/user_guide/Advanced/Command%20line%20interface
    Report errors or feedback here: https://github.com/Pioreactor/pioreactor/issues
    """


@pio.command(name="logs", short_help="show recent logs")
@click.option("-n", type=int, default=100)
def logs(n: int) -> None:
    """
    Tail & stream the logs from this unit to the terminal. CTRL-C to exit.
    """
    from sh import tail  # type: ignore
    from json import loads
    import time
    from signal import pause

    def cb(msg) -> None:
        payload = loads(msg.payload.decode())

        # time module is used below because it is the same that the logging module uses: https://docs.python.org/3/library/logging.html#logging.Formatter.formatTime
        click.echo(
            f"{time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime())} [{payload['task']}] {payload['level']} {payload['message']}"
        )

    click.echo(tail("-n", n, config["logging"]["log_file"]))

    try:
        # will fail if not connected to leader.
        subscribe_and_callback(cb, f"pioreactor/{get_unit_name()}/+/logs/+")
    except OSError:
        pass

    pause()


@pio.command(name="blink", short_help="blink LED")
def blink() -> None:

    with local_intermittent_storage("pio_jobs_running") as cache:
        monitor_running = cache.get("monitor", b"0") == b"1"

    if not monitor_running:

        import RPi.GPIO as GPIO  # type: ignore

        GPIO.setmode(GPIO.BCM)

        from pioreactor.hardware import PCB_LED_PIN as LED_PIN

        def led_on() -> None:
            GPIO.output(LED_PIN, GPIO.HIGH)

        def led_off() -> None:
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

    else:
        publish(f"pioreactor/{get_unit_name()}/.../monitor/flicker_led_response_okay", 1)


@pio.command(name="kill", short_help="kill job(s)")
@click.argument("job", nargs=-1)
@click.option("--all-jobs", is_flag=True, help="kill all Pioreactor jobs running")
def kill(job: str, all_jobs: bool) -> None:
    """
    stop a job by sending a SIGTERM to it.
    """

    from sh import pkill  # type: ignore

    def safe_pkill(*args: str) -> None:
        try:
            pkill(*args)
        except Exception:
            pass

    if all_jobs:
        safe_pkill("-f", "pio run ")
    else:
        for j in job:
            safe_pkill("-f", f"pio run {j}")
            safe_pkill("-f", f"pio run-always {j}")


@pio.group(short_help="run a job")
def run() -> None:
    pass


@pio.group(name="run-always", short_help="run a long-lived job")
def run_always() -> None:
    pass


@pio.command(name="version", short_help="print the Pioreactor software version")
@click.option("--verbose", "-v", is_flag=True, help="show more system information")
def version(verbose: bool) -> None:

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
def view_cache(cache: str) -> None:
    import os.path

    from pioreactor.utils import local_intermittent_storage, local_persistant_storage

    # is it a temp cache?
    if os.path.isfile(f"/tmp/{cache}.db") or os.path.isfile(f"/tmp/{cache}.pag"):
        cacher = local_intermittent_storage
    elif os.path.isfile(f".pioreactor/storage/{cache}.db") or os.path.isfile(
        f".pioreactor/storage/{cache}.pag"
    ):
        cacher = local_persistant_storage
    else:
        click.echo(f"cache {cache} not found.")
        return

    with cacher(cache) as c:
        for key in sorted(c.keys()):
            click.echo(f"{key.decode()} = {c[key].decode()}")


@pio.command(name="update", short_help="update the Pioreactor software (app and/or UI)")
@click.option("--ui", is_flag=True, help="update the PioreactorUI to latest")
@click.option("--app", is_flag=True, help="update the Pioreactor to latest")
@click.option("-b", "--branch", help="update to a branch on github")
def update(ui: bool, app: bool, branch: Optional[str]) -> None:
    import subprocess
    from json import loads
    from pioreactor.mureq import get

    logger = create_logger(
        "update", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT
    )

    if (not app) and (not ui):
        click.echo("Nothing to do. Specify either --app or --ui.")

    if app:

        if branch is None:
            latest_release_metadata = loads(
                get(
                    "https://api.github.com/repos/pioreactor/pioreactor/releases/latest"
                ).body
            )
            version_installed = latest_release_metadata["name"]
            url_to_get_whl = f"https://github.com/Pioreactor/pioreactor/releases/download/{version_installed}/pioreactor-{version_installed}-py3-none-any.whl"

            command = f'sudo pip3 install "pioreactor @ {url_to_get_whl}"'
        else:
            version_installed = branch
            command = f"sudo pip3 install -U --force-reinstall https://github.com/pioreactor/pioreactor/archive/{branch}.zip"

        p = subprocess.run(
            command,
            shell=True,
            universal_newlines=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if p.returncode == 0:
            logger.info(f"Updated Pioreactor to version {version_installed}.")
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
    run.add_command(actions.pump_calibration.click_pump_calibration)

    for plugin in pioreactor.plugin_management.get_plugins().values():
        for possible_entry_point in dir(plugin.module):
            if possible_entry_point.startswith("click_"):
                run.add_command(getattr(plugin.module, possible_entry_point))


if am_I_leader():
    run_always.add_command(jobs.mqtt_to_db_streaming.click_mqtt_to_db_streaming)
    run_always.add_command(jobs.watchdog.click_watchdog)

    run.add_command(actions.export_experiment_data.click_export_experiment_data)
    run.add_command(actions.backup_database.click_backup_database)

    @pio.command(short_help="access the db CLI")
    def db() -> None:
        import os

        os.system(f"sqlite3 {config['storage']['database']}")

    @pio.command(short_help="tail MQTT")
    @click.option("--topic", "-t", default="pioreactor/#")
    def mqtt(topic: str) -> None:
        import os

        os.system(f"""mosquitto_sub -v -t '{topic}' -F "%I %t %p" """)

    @pio.command(name="add-pioreactor", short_help="add a new Pioreactor to cluster")
    @click.argument("new_name")
    def add_pioreactor(new_name: str) -> None:
        """
        Add a new pioreactor worker to the cluster. The pioreactor should already have the worker image installed and is turned on.

        """
        # TODO: move this to its own file
        import socket
        import subprocess

        logger = create_logger(
            "add_pioreactor", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT
        )
        logger.info(f"Adding new pioreactor {new_name} to cluster.")

        # check to make sure new_name isn't already on the network

        # check to make sure raspberrypi.local is on network
        checks, max_checks = 0, 20
        while not networking.is_hostname_on_network(new_name):
            checks += 1
            try:
                socket.gethostbyname(new_name)
            except socket.gaierror:
                sleep(3)
                click.echo(f"`{new_name}` not found on network - checking again.")
                if checks >= max_checks:
                    logger.error(
                        f"`{new_name}` not found on network after {max_checks} seconds. Check that you provided the right WiFi credentials to the network, and that the Raspberry Pi is turned on."
                    )
                    sys.exit(1)

        res = subprocess.call(
            [
                "bash /usr/local/bin/add_new_pioreactor_worker_from_leader.sh %s"
                % (new_name)
            ],
            shell=True,
        )
        if res == 0:
            logger.info(f"New pioreactor {new_name} successfully added to cluster.")

    @pio.command(
        name="cluster-status", short_help="report information on the pioreactor cluster"
    )
    def cluster_status() -> None:

        click.secho(
            f"{'Unit / hostname':20s} {'Is leader?':15s} {'IP address':20s} {'State':15s} {'Reachable?':10s}",
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
