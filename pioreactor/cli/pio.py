# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring --ignore-rpm
> pio logs
"""
from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from json import dumps
from json import loads
from shlex import quote
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
from pioreactor.mureq import get
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.gpio_helpers import temporarily_set_gpio_unavailable
from pioreactor.utils.networking import add_local


@click.group(invoke_without_command=True)
@click.pass_context
def pio(ctx) -> None:
    """
    Execute commands on this Pioreactor.
    See full documentation here: https://docs.pioreactor.com/user-guide/cli
    Report errors or feedback here: https://github.com/Pioreactor/pioreactor/issues
    """

    # if a user runs `pio`, we want the check_firstboot_successful to run, hence the invoke_without_command
    # https://click.palletsprojects.com/en/8.1.x/commands/#group-invocation-without-command
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

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
    TODO: this consumes a full CPU core!
    """

    def file_len(filename) -> int:
        count = 0
        with open(filename) as f:
            for _ in f:
                count += 1
        return count

    def follow(filename, sleep_sec=0.2):
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
        click.echo(line, nl=False)


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
@click.option("--local-only", is_flag=True, help="don't send to MQTT; write only to local disk")
def log(message: str, level: str, name: str, local_only: bool):
    try:
        logger = create_logger(
            name,
            unit=whoami.get_unit_name(),
            experiment=whoami.UNIVERSAL_EXPERIMENT,
            to_mqtt=not local_only,
        )
        getattr(logger, level)(message)
    except Exception:
        # don't let a logging error bring down a script...
        pass


@pio.command(name="blink", short_help="blink LED")
def blink() -> None:

    monitor_running = is_pio_job_running("monitor")

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
def kill(job: list[str], all_jobs: bool) -> None:
    """
    stop a job(s).
    """
    """
    This isn't a very clean way to end jobs (generally: actions). Ex: If a python script is running with Pioreactor jobs
    running in it, it won't get closed.

    Another approach is to iterate through /tmp/job_metadata_*.db and fire an MQTT event to kill them. This would fail though if
    not connected to leader...

    Another option is for _all jobs and actions_ to listen to a special topic: pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/{whoami.UNIVERSAL_EXPERIMENT}/kill
    A single publish is sent, and everyone kills themselves. This fails if not connected to a leader.

    Another option is to send a kill signal to the process_id, which is in both pio_jobs_running and job metadata. This doesn't rely on MQTT, so
    no leader connection is required.
    """

    from sh import pkill  # type: ignore
    from pioreactor.actions.led_intensity import led_intensity

    def safe_pkill(*args: str) -> None:
        try:
            pkill(*args)
        except Exception:
            pass

    if all_jobs:
        # kill all running pioreactor processes
        safe_pkill("-f", "pio run ")

        # kill all pumping
        with pubsub.create_client() as client:
            client.publish(
                f"pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/{whoami.UNIVERSAL_EXPERIMENT}/add_media/$state/set",
                "disconnected",
                qos=pubsub.QOS.AT_LEAST_ONCE,
            )
            client.publish(
                f"pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/{whoami.UNIVERSAL_EXPERIMENT}/remove_waste/$state/set",
                "disconnected",
                qos=pubsub.QOS.AT_LEAST_ONCE,
            )
            client.publish(
                f"pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/{whoami.UNIVERSAL_EXPERIMENT}/add_alt_media/$state/set",
                "disconnected",
                qos=pubsub.QOS.AT_LEAST_ONCE,
            )

        # kill all LEDs
        sleep(0.5)
        led_intensity({"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0}, verbose=False)

        # assert everything is off
        with local_intermittent_storage("pwm_dc") as cache:
            for pin in cache:
                assert cache[pin] == 0.0, f"pin {pin} is not off!"

        # assert everything is off
        with local_intermittent_storage("leds") as cache:
            for led in cache:
                assert cache[led] == 0.0, f"LED {led} is not off!"

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
        raise click.Abort()


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
        from pioreactor.version import serial_number
        from pioreactor.version import tuple_to_text
        from pioreactor.version import get_firmware_version

        click.echo(f"Pioreactor software:    {tuple_to_text(software_version_info)}")
        click.echo(f"Pioreactor HAT:         {tuple_to_text(hardware_version_info)}")
        click.echo(f"Pioreactor firmware:    {tuple_to_text(get_firmware_version())}")
        click.echo(f"HAT serial number:      {serial_number}")
        click.echo(f"Operating system:       {platform.platform()}")
        click.echo(f"Raspberry Pi:           {whoami.get_rpi_machine()}")
        if whoami.am_I_leader():
            try:
                click.echo(
                    f"Pioreactor UI:          {get('http://127.0.0.1/api/ui_version').body.decode()}"
                )
            except Exception:
                pass
    else:
        click.echo(pioreactor.__version__)


@pio.command(name="view-cache", short_help="print out the contents of a cache")
@click.argument("cache")
def view_cache(cache: str) -> None:
    import os.path
    import tempfile

    tmp_dir = tempfile.gettempdir()

    # is it a temp cache or persistant cache?
    if os.path.isdir(f"{tmp_dir}/{cache}"):
        cacher = local_intermittent_storage

    elif os.path.isdir(f".pioreactor/storage/{cache}"):
        cacher = local_persistant_storage

    else:
        click.echo(f"cache {cache} not found.")
        return

    with cacher(cache) as c:
        for key in sorted(list(c.iterkeys())):
            click.echo(f"{click.style(key, bold=True)} = {c[key]}")


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
        pubsub.publish(
            f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value, qos=pubsub.QOS.EXACTLY_ONCE
        )


@pio.group()
def update() -> None:
    pass


@update.command(name="app")
@click.option("-b", "--branch", help="update to a branch on github")
@click.option("--source", help="use a URL or whl file")
@click.option("-v", "--version", help="install a specific version, default is latest")
def update_app(branch: Optional[str], source: Optional[str], version: Optional[str]) -> None:
    """
    Update the Pioreactor core software
    """
    logger = create_logger(
        "update-app", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT
    )

    commands_and_priority: list[tuple[str, float]] = []

    if version is None:
        version = "latest"
    else:
        version = f"tags/{version}"

    if source is not None:
        version_installed = source
        commands_and_priority.append((f"sudo pip3 install -U --force-reinstall {source}", 1))

    elif branch is not None:
        version_installed = quote(branch)
        commands_and_priority.append(
            (
                f"sudo pip3 install -U --force-reinstall https://github.com/pioreactor/pioreactor/archive/{branch}.zip",
                1,
            )
        )

    else:
        release_metadata = loads(
            get(f"https://api.github.com/repos/pioreactor/pioreactor/releases/{version}").body
        )
        version_installed = release_metadata["tag_name"]
        for asset in release_metadata["assets"]:
            # TODO: potential supply chain attack is to add malicious assets to releases
            if asset["name"].endswith(".whl") and asset["name"].startswith("pioreactor"):
                url_to_get_whl = asset["browser_download_url"]
                commands_and_priority.append(
                    (
                        f'sudo pip3 install "pioreactor @ {url_to_get_whl}"',
                        1,
                    )
                )
            elif asset["name"] == "update.sh":
                url_to_get_sh = asset["browser_download_url"]
                commands_and_priority.extend(
                    [
                        (f"wget -O /tmp/update.sh {url_to_get_sh}", 2.0),
                        ("sudo bash /tmp/update.sh", 2.1),
                    ]
                )
            elif asset["name"] == "update.sql":
                url_to_get_sql = asset["browser_download_url"]
                commands_and_priority.extend(
                    [
                        (f"wget -O /tmp/update.sql {url_to_get_sql}", 3.0),
                        (f'sudo sqlite3 {config["storage"]["database"]} < /tmp/update.sql', 3.1),
                    ]
                )

    for command, _ in sorted(commands_and_priority, key=lambda t: t[1]):
        logger.debug(command)
        p = subprocess.run(
            command,
            shell=True,
            universal_newlines=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if p.returncode != 0:
            logger.debug(p.stderr)
            logger.error("Update failed. See logs.")
            # end early
            return

    logger.notice(f"Updated Pioreactor to version {version_installed}.")  # type: ignore


@update.command(name="firmware")
@click.option("-b", "--branch", help="update to a branch on github")
def update_firmware(branch: Optional[str]) -> None:
    # TODO
    return


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

        os.system(f"sqlite3 {config['storage']['database']} -column -header")

    @pio.command(short_help="tail MQTT")
    @click.option("--topic", "-t", default="pioreactor/#")
    def mqtt(topic: str) -> None:
        import os

        os.system(
            f"""mosquitto_sub -v -t '{topic}' -F "%19.19I  |  %t   %p" -u pioreactor -P raspberry"""
        )

    @pio.command(name="add-pioreactor", short_help="add a new Pioreactor to cluster")
    @click.argument("hostname")
    def add_pioreactor(hostname: str) -> None:
        """
        Add a new pioreactor worker to the cluster. The pioreactor should already have the worker image installed and is turned on.

        hostname is without any .local.
        """
        # TODO: move this to its own file
        import socket

        logger = create_logger(
            "add_pioreactor",
            unit=whoami.get_unit_name(),
            experiment=whoami.UNIVERSAL_EXPERIMENT,
        )
        logger.info(f"Adding new pioreactor {hostname} to cluster.")

        hostname = hostname.removesuffix(".local")
        hostname_dot_local = hostname + ".local"

        # check to make sure hostname.local is on network
        checks, max_checks = 0, 20
        sleep_time = 3
        while not networking.is_hostname_on_network(hostname_dot_local):
            checks += 1
            try:
                socket.gethostbyname(hostname_dot_local)
            except socket.gaierror:
                sleep(sleep_time)
                click.echo(f"`{hostname}` not found on network - checking again.")
                if checks >= max_checks:
                    logger.error(
                        f"`{hostname}` not found on network after more than {max_checks * sleep_time} seconds. Check that you provided the right WiFi credentials to the network, and that the Raspberry Pi is turned on."
                    )
                    raise click.Abort()

        res = subprocess.run(
            ["bash", "/usr/local/bin/add_new_pioreactor_worker_from_leader.sh", hostname],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            logger.notice(f"New pioreactor {hostname} successfully added to cluster.")  # type: ignore
        else:
            logger.error(res.stderr)
            raise click.Abort()

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
                    ip = "unknown"

            # get state
            result = pubsub.subscribe(
                f"pioreactor/{hostname}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/$state",
                timeout=1,
                name="CLI",
            )
            if result:
                state = result.payload.decode()
            else:
                state = "unknown"

            # is reachable?
            reachable = networking.is_reachable(add_local(hostname))

            return ip, state, reachable

        def display_data_for(hostname_status) -> bool:
            hostname, status = hostname_status

            ip, state, reachable = get_network_metadata(hostname)

            statef = click.style(f"{state:15s}", fg="green" if state == "ready" else "red")
            ipf = f"{ip if (ip is not None) else 'unknown':20s}"

            is_leaderf = f"{('Y' if hostname==get_leader_hostname() else 'N'):15s}"
            hostnamef = f"{hostname:20s}"
            reachablef = f"{(click.style('Y', fg='green') if reachable       else click.style('N', fg='red')):23s}"
            statusf = f"{(click.style('Y', fg='green') if (status == '1') else click.style('N', fg='red')):14s}"

            click.echo(f"{hostnamef} {is_leaderf} {ipf} {statef} {reachablef} {statusf}")
            return reachable & (state == "ready")

        worker_statuses = list(config["cluster.inventory"].items())
        n_workers = len(worker_statuses)

        click.secho(
            f"{'Unit / hostname':20s} {'Is leader?':15s} {'IP address':20s} {'State':15s} {'Reachable?':14s} {'Active?':14s}",
            bold=True,
        )
        if n_workers == 0:
            return

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            results = executor.map(display_data_for, worker_statuses)

        if not all(results):
            raise click.Abort()

    @update.command(name="ui")
    @click.option("-b", "--branch", help="update to a branch on github")
    @click.option("--source", help="use a tar.gz file")
    @click.option("-v", "--version", help="install a specific version")
    def update_ui(branch: Optional[str], source: Optional[str], version: Optional[str]) -> None:
        """
        Update the PioreactorUI

        Source, if provided, should be a .tar.gz with a top-level dir like pioreactorui-{branch}/
        This is what is provided from Github releases.
        """
        logger = create_logger(
            "update-ui", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT
        )
        commands = []

        if version is None:
            version = "latest"
        else:
            version = f"tags/{version}"

        if source is not None:
            version_installed = branch
            assert branch is not None, "branch must be provided with the -b option"

        elif branch is not None:
            version_installed = quote(branch)
            url = f"https://github.com/Pioreactor/pioreactorui/archive/{branch}.tar.gz"
            source = "/tmp/pioreactorui.tar.gz"
            commands.append(["wget", url, "-O", source])

        else:
            latest_release_metadata = loads(
                get(f"https://api.github.com/repos/pioreactor/pioreactorui/releases/{version}").body
            )
            version_installed = latest_release_metadata["tag_name"]
            url = f"https://github.com/Pioreactor/pioreactorui/archive/refs/tags/{version_installed}.tar.gz"
            source = "/tmp/pioreactorui.tar.gz"
            commands.append(["wget", url, "-O", source])

        assert source is not None
        assert version_installed is not None
        commands.append(["bash", "/usr/local/bin/update_ui.sh", source, version_installed])

        for command in commands:
            logger.debug(" ".join(command))
            p = subprocess.run(
                command,
                universal_newlines=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if p.returncode != 0:
                logger.error(p.stderr)
                raise click.Abort()

        logger.notice(f"Updated PioreactorUI to version {version_installed}.")  # type: ignore
