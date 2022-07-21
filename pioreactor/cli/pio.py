# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run od_reading
> pio run stirring --ignore-rpm
> pio log
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from json import dumps
from time import sleep
from typing import Optional

import click

import pioreactor
import pioreactor.utils.networking as networking
from pioreactor import actions
from pioreactor import background_jobs as jobs
from pioreactor import plugin_management
from pioreactor import pubsub
from pioreactor import whoami
from pioreactor.config import check_firstboot_successful
from pioreactor.config import config
from pioreactor.config import get_leader_hostname
from pioreactor.logging import create_logger
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.gpio_helpers import temporarily_set_gpio_unavailable
from pioreactor.utils.networking import add_local


@click.group()
def pio() -> None:
    """
    Execute commands on this Pioreactor.
    See full documentation here: https://docs.pioreactor.com/user_guide/Advanced/Command%20line%20interface
    Report errors or feedback here: https://github.com/Pioreactor/pioreactor/issues
    """

    # this check could go somewhere else. This check won't execute if calling pioreactor from a script.
    if not check_firstboot_successful():
        raise SystemError(
            "/usr/local/bin/firstboot.sh found on disk. firstboot.sh likely failed. Try looking for errors in `sudo systemctl status firstboot.service`."
        )


@pio.command(name="logs", short_help="show recent logs")
@click.option(
    "-n",
    default=100,
    type=int,
)
def logs(n) -> None:
    """
    Tail & stream the logs from this unit to the terminal. CTRL-C to exit.
    """

    def file_len(filename) -> int:
        with open(filename) as f:
            for i, _ in enumerate(f):
                pass
        return i + 1

    def follow(filename, sleep_sec=0.1):
        """Yield each line from a file as they are written.
        `sleep_sec` is the time to sleep after empty reads."""

        # count the number of lines
        n_lines = file_len(filename)

        with open(filename) as file:
            line = ""
            count = 1
            while True:
                tmp = file.readline()
                count += 1
                if tmp is not None:
                    line += tmp
                    if line.endswith("\n") and count > (n_lines - n):
                        yield line
                    line = ""
                else:
                    sleep(sleep_sec)

    for line in follow(config["logging"]["log_file"]):
        print(line, end="")


@pio.command(name="log", short_help="logs a message from the CLI")
@click.option("-m", "--message", required=True, type=str, help="the message to append to the log")
@click.option(
    "-l",
    "--level",
    default="debug",
    type=click.Choice(["debug", "info", "notice", "warning", "critical"], case_sensitive=False),
)
@click.option(
    "-n",
    "--name",
    default="CLI",
    type=str,
)
def log(message, level, name):
    logger = create_logger(
        name, unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT
    )
    getattr(logger, level)(message)
    return


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
        pubsub.publish(
            f"pioreactor/{whoami.get_unit_name()}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/flicker_led_response_okay",
            1,
        )


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
    if not (whoami.am_I_active_worker() or whoami.am_I_leader()):
        click.echo(
            f"Running `pio` on a non-active Pioreactor. Do you need to change `{whoami.get_unit_name()}` in `cluster.inventory` section in `config.ini`?"
        )
        sys.exit(1)


@pio.group(name="run-always", short_help="run a long-lived job")
def run_always() -> None:
    pass


@pio.command(name="version", short_help="print the Pioreactor software version")
@click.option("--verbose", "-v", is_flag=True, help="show more system information")
def version(verbose: bool) -> None:
    if verbose:
        import platform
        from pioreactor.version import hardware_version_info
        from pioreactor.version import software_version_info
        from pioreactor.version import tuple_to_text

        # TODO include HAT version and latest git shas
        click.echo(f"Pioreactor software:    {tuple_to_text(software_version_info)}")
        click.echo(f"Pioreactor HAT:         {tuple_to_text(hardware_version_info)}")
        click.echo(f"Operating system:       {platform.platform()}")
        click.echo(f"Raspberry Pi:           {whoami.get_rpi_machine()}")
    else:
        click.echo(pioreactor.__version__)


@pio.command(name="view-cache", short_help="print out the contents of a cache")
@click.argument("cache")
def view_cache(cache: str) -> None:
    import os.path

    from pioreactor.utils import local_intermittent_storage, local_persistant_storage

    # is it a temp cache?
    tmp_dir = os.environ.get("TMPDIR") or os.environ.get("TMP") or "/tmp/"
    if (
        os.path.isfile(f"{tmp_dir}{cache}.db")
        or os.path.isfile(f"{tmp_dir}{cache}.pag")
        or os.path.isfile(f"{tmp_dir}{cache}")
    ):
        cacher = local_intermittent_storage

    elif (
        os.path.isfile(f".pioreactor/storage/{cache}.db")
        or os.path.isfile(f".pioreactor/storage/{cache}.pag")
        or os.path.isfile(f"{tmp_dir}{cache}")
    ):
        cacher = local_persistant_storage

    else:
        click.echo(f"cache {cache} not found.")
        return

    with cacher(cache) as c:
        for key in sorted(c.keys()):
            click.echo(f"{key.decode()} = {c[key].decode()}")


@pio.command(
    name="update-settings",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
    short_help="update settings on a running job",
)
@click.argument("job", type=click.STRING)
@click.pass_context
def update_settings(ctx, job: str) -> None:
    """
    Examples
    ----------

    > pio update-settings stirring --target_rpm 500
    > pio update-settings dosing_control --automation '{"type": "dosing", "automation_name": "silent", "args": {}}

    """
    exp = whoami.get_latest_experiment_name()
    unit = whoami.get_unit_name()

    extra_args = {ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)}

    assert len(extra_args) > 0

    for (setting, value) in extra_args.items():
        pubsub.publish(f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value)
        pubsub.publish(f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value)


@pio.command(name="update", short_help="update the Pioreactor software (app and/or UI)")
@click.option("--ui", is_flag=True, help="update the PioreactorUI to latest")
@click.option("--app", is_flag=True, help="update the Pioreactor to latest")
@click.option("-b", "--branch", help="update to a branch on github")
def update(ui: bool, app: bool, branch: Optional[str]) -> None:
    import subprocess
    from json import loads
    from pioreactor.mureq import get

    logger = create_logger(
        "update", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT
    )

    if (not app) and (not ui):
        click.echo("Nothing to do. Specify either --app or --ui.")

    if app:

        if branch is None:
            latest_release_metadata = loads(
                get("https://api.github.com/repos/pioreactor/pioreactor/releases/latest").body
            )
            version_installed = latest_release_metadata["name"]
            url_to_get_whl = f"https://github.com/Pioreactor/pioreactor/releases/download/{version_installed}/pioreactor-{version_installed}-py3-none-any.whl"

            command = (
                f'sudo pip3 install --disable-pip-version-check "pioreactor @ {url_to_get_whl}"'
            )
        else:
            version_installed = branch
            command = f"sudo pip3 install --disable-pip-version-check -U --force-reinstall https://github.com/pioreactor/pioreactor/archive/{branch}.zip"

        p = subprocess.run(
            command,
            shell=True,
            universal_newlines=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if p.returncode == 0:
            logger.notice(f"Updated Pioreactor to version {version_installed}.")  # type: ignore
        else:
            logger.error(p.stderr)

    if ui and whoami.am_I_leader():
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
            logger.notice("Updated PioreactorUI to latest version.")  # type: ignore
        else:
            logger.error(p.stderr)


pio.add_command(plugin_management.click_install_plugin)
pio.add_command(plugin_management.click_uninstall_plugin)
pio.add_command(plugin_management.click_list_plugins)

# this runs on both leader and workers
run_always.add_command(jobs.monitor.click_monitor)


if whoami.am_I_active_worker():
    run.add_command(jobs.growth_rate_calculating.click_growth_rate_calculating)
    run.add_command(jobs.stirring.click_stirring)
    run.add_command(jobs.od_reading.click_od_reading)
    run.add_command(jobs.dosing_control.click_dosing_control)
    run.add_command(jobs.led_control.click_led_control)
    run.add_command(jobs.temperature_control.click_temperature_control)

    run.add_command(actions.pump.click_add_alt_media)
    run.add_command(actions.led_intensity.click_led_intensity)
    run.add_command(actions.pump.click_add_media)
    run.add_command(actions.pump.click_remove_waste)
    run.add_command(actions.od_blank.click_od_blank)
    run.add_command(actions.self_test.click_self_test)
    run.add_command(actions.stirring_calibration.click_stirring_calibration)
    run.add_command(actions.pump_calibration.click_pump_calibration)

    for plugin in pioreactor.plugin_management.get_plugins().values():
        for possible_entry_point in dir(plugin.module):
            if possible_entry_point.startswith("click_"):
                run.add_command(getattr(plugin.module, possible_entry_point))


if whoami.am_I_leader():
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
    @click.argument("hostname")
    def add_pioreactor(hostname: str) -> None:
        """
        Add a new pioreactor worker to the cluster. The pioreactor should already have the worker image installed and is turned on.

        hostname is without any .local.
        """
        # TODO: move this to its own file
        import socket
        import subprocess

        logger = create_logger(
            "add_pioreactor",
            unit=whoami.get_unit_name(),
            experiment=whoami.UNIVERSAL_EXPERIMENT,
        )
        logger.info(f"Adding new pioreactor {hostname} to cluster.")

        hostname = hostname.removesuffix(".local")
        hostname_dot_local = hostname + ".local"

        # check to make sure hostname isn't already on the network

        # check to make sure X.local is on network
        checks, max_checks = 0, 20
        while not networking.is_hostname_on_network(hostname_dot_local):
            checks += 1
            try:
                socket.gethostbyname(hostname_dot_local)
            except socket.gaierror:
                sleep(3)
                click.echo(f"`{hostname}` not found on network - checking again.")
                if checks >= max_checks:
                    logger.error(
                        f"`{hostname}` not found on network after {max_checks} seconds. Check that you provided the right WiFi credentials to the network, and that the Raspberry Pi is turned on."
                    )
                    sys.exit(1)

        res = subprocess.call(
            [f"bash /usr/local/bin/add_new_pioreactor_worker_from_leader.sh {hostname}"],
            shell=True,
        )
        if res == 0:
            logger.notice(f"New pioreactor {hostname} successfully added to cluster.")  # type: ignore

    @pio.command(
        name="discover-workers",
        short_help="discover all pioreactor workers on the network",
    )
    @click.option("--json", is_flag=True, help="output as json")
    def discover_workers(json) -> None:
        from pioreactor.utils.networking import discover_workers_on_network

        if json:
            click.echo(dumps({"workers": discover_workers_on_network()}))
        else:
            for hostname in discover_workers_on_network():
                click.echo(hostname)

    @pio.command(name="cluster-status", short_help="report information on the pioreactor cluster")
    def cluster_status() -> None:
        """
        Note that this only looks at the current cluster as defined in config.ini.
        """
        import socket

        def get_network_metadata(hostname):
            # get ip
            if whoami.get_unit_name() == hostname:
                ip = networking.get_ip()
            else:
                try:
                    ip = socket.gethostbyname(add_local(hostname))
                except OSError:
                    ip = "Unknown"

            # get state
            result = pubsub.subscribe(
                f"pioreactor/{hostname}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/$state",
                timeout=1,
                name="CLI",
            )
            if result:
                state = result.payload.decode()
            else:
                state = "Unknown"

            # is reachable?
            reachable = networking.is_reachable(add_local(hostname))

            return ip, state, reachable

        def display_data_for(hostname_status) -> bool:
            hostname, status = hostname_status

            ip, state, reachable = get_network_metadata(hostname)

            statef = click.style(f"{state:15s}", fg="green" if state == "ready" else "red")
            ipf = f"{ip:20s}"

            reachablef = f"{(  click.style('Y', fg='green') if reachable else click.style('N', fg='red') ):10s}"
            is_leaderf = f"{('Y' if hostname==get_leader_hostname() else 'N'):15s}"
            hostnamef = f"{hostname:20s}"
            status = "Y" if status == "1" else "N"

            click.echo(f"{hostnamef} {is_leaderf} {ipf} {statef} {reachablef} {status}")
            return reachable & (state == "ready")

        click.secho(
            f"{'Unit / hostname':20s} {'Is leader?':15s} {'IP address':20s} {'State':15s} {'Reachable?':10s} {'Active?' :10s}",
            bold=True,
        )

        units_statuses = list(config["cluster.inventory"].items())
        with ThreadPoolExecutor(max_workers=len(units_statuses)) as executor:
            results = executor.map(display_data_for, units_statuses)

        if not all(results):
            sys.exit(1)
