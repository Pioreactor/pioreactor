# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring --ignore-rpm
> pio logs
"""
from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from json import loads
from shlex import quote
from sys import exit
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


JOBS_TO_SKIP_KILLING = [
    # this is used in `pio kill --all-jobs`, but accessible so that plugins can edit it.
    # don't kill our permanent jobs
    "monitor",
    "watchdog",
    "mqtt_to_db_streaming",
    # don't kill automations, let the parent controller do it.
    # probably all BackgroundSubJob should be here.
    "temperature_automation",
    "dosing_automation",
    "led_automation",
]


@click.group(invoke_without_command=True)
@click.pass_context
def pio(ctx) -> None:
    """
    Execute commands on this Pioreactor.

    Configuration available: /home/pioreactor/.pioreactor/config.ini

    See full documentation: https://docs.pioreactor.com/user-guide/cli

    Report errors or feedback: https://github.com/Pioreactor/pioreactor/issues
    """

    # if a user runs `pio`, we want the check_firstboot_successful to run, hence the invoke_without_command
    # https://click.palletsprojects.com/en/8.1.x/commands/#group-invocation-without-command
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

    # this check could go somewhere else. TODO This check won't execute if calling pioreactor from a script.
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
def logs(n: int) -> None:
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

    except Exception as e:
        # don't let a logging error bring down a script...
        print(e)


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
    stop job(s).
    """

    from sh import kill  # type: ignore
    from pioreactor.actions.led_intensity import led_intensity

    def safe_kill(*args: int) -> None:
        try:
            kill(*args)
        except Exception:
            pass

    if all_jobs:
        # kill all running pioreactor processes
        jobs_killed_already = []
        with local_intermittent_storage("pio_jobs_running") as cache:
            for j in cache:
                if j not in JOBS_TO_SKIP_KILLING:
                    pid = cache[j]
                    if pid not in jobs_killed_already:
                        safe_kill(int(pid))
                        jobs_killed_already.append(pid)

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
        sleep(0.25)
        try:
            # non-workers won't have this hardware, so just skip it
            led_intensity({"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0}, verbose=False)
        except Exception:
            pass

        # assert everything is off
        with local_intermittent_storage("pwm_dc") as cache:
            for pin in cache:
                if cache[pin] != 0.0:
                    print(f"pin {pin} is not off!")

        # assert everything is off
        with local_intermittent_storage("leds") as cache:
            for led in cache:
                if cache[led] != 0.0:
                    print(f"LED {led} is not off!")

    else:
        jobs_killed_already = []
        with local_intermittent_storage("pio_jobs_running") as cache:
            for j in cache:
                if j in job:
                    pid = cache[j]
                    if pid not in jobs_killed_already:
                        safe_kill(int(pid))
                        jobs_killed_already.append(pid)


@pio.group(short_help="run a job")
def run() -> None:
    if not (whoami.am_I_active_worker() or whoami.am_I_leader()):
        click.echo(
            f"Running `pio` on a non-active Pioreactor. Do you need to change `{whoami.get_unit_name()}` in `cluster.inventory` section in `config.ini`?"
        )
        raise click.Abort()


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
        click.echo(f"Image version:          {whoami.get_image_git_hash()}")
        if whoami.am_I_leader():
            try:
                result = get("http://127.0.0.1/api/versions/ui")
                result.raise_for_status()
                ui_version = result.body.decode()
            except Exception:
                ui_version = "<Failed to fetch>"

            click.echo(f"Pioreactor UI:          {ui_version}")
    else:
        click.echo(pioreactor.__version__)


@pio.command(name="view-cache", short_help="print out the contents of a cache")
@click.argument("cache")
def view_cache(cache: str) -> None:
    import os.path
    import tempfile

    tmp_dir = tempfile.gettempdir()

    persistant_dir = (
        "/home/pioreactor/.pioreactor/storage/"
        if not whoami.is_testing_env()
        else ".pioreactor/storage"
    )

    # is it a temp cache or persistant cache?
    if os.path.isdir(f"{tmp_dir}/{cache}"):
        cacher = local_intermittent_storage

    elif os.path.isdir(f"{persistant_dir}/{cache}"):
        cacher = local_persistant_storage

    else:
        click.echo(f"cache {cache} not found.")
        return

    with cacher(cache) as c:
        for key in sorted(list(c.iterkeys())):
            click.echo(f"{click.style(key, bold=True)} = {c[key]}")


@pio.command(name="clear-cache", short_help="clear out the contents of a cache")
@click.argument("cache")
@click.argument("key")
def clear_cache(cache: str, key: str) -> None:
    import os.path
    import tempfile

    tmp_dir = tempfile.gettempdir()

    persistant_dir = (
        "/home/pioreactor/.pioreactor/storage/"
        if not whoami.is_testing_env()
        else ".pioreactor/storage"
    )

    # is it a temp cache or persistant cache?
    if os.path.isdir(f"{tmp_dir}/{cache}"):
        cacher = local_intermittent_storage

    elif os.path.isdir(f"{persistant_dir}/{cache}"):
        cacher = local_persistant_storage

    else:
        click.echo(f"cache {cache} not found.")
        return

    with cacher(cache) as c:
        if key in c:
            del c[key]


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
    > pio update-settings stirring --target-rpm 500
    > pio update-settings dosing_control --automation '{"type": "dosing", "automation_name": "silent", "args": {}}

    """
    exp = whoami.get_latest_experiment_name()
    unit = whoami.get_unit_name()

    extra_args = {ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)}

    assert len(extra_args) > 0

    for setting, value in extra_args.items():
        setting = setting.replace("-", "_")
        pubsub.publish(
            f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value, qos=pubsub.QOS.EXACTLY_ONCE
        )


@pio.group()
def update() -> None:
    """
    Update software for the app and UI
    """
    pass


def get_non_prerelease_tags_of_pioreactor(repo):
    """
    Returns a list of all the tag names associated with non-prerelease releases, sorted in descending order
    """
    url = f"https://api.github.com/repos/{repo}/releases"
    headers = {"Accept": "application/vnd.github.v3+json"}
    response = get(url, headers=headers)

    if not response.ok:
        raise Exception(f"Failed to retrieve releases (status code: {response.status_code})")

    releases = response.json()
    non_prerelease_tags = []

    for release in releases:
        if not release["prerelease"]:
            non_prerelease_tags.append(release["tag_name"])

    def version_key(version):
        major, minor, patch = version.split(".")
        return int(major), int(minor), int(patch)

    return sorted(non_prerelease_tags, reverse=True, key=version_key)


def get_tag_to_install(repo: str, version_desired: Optional[str]) -> str:
    """
    The function get_tag_to_install takes an optional argument version_desired and
    returns a string that represents the tag of a particular version of software to install.

    If version_desired is not provided or is None, the function determines the latest
    non-prerelease version of the software installed on the system, and returns the tag
    of the previous version as a string, or "latest" if the system is already up to date.

    If version_desired is provided and is "latest", the function returns "latest" as a string.

    Otherwise, the function returns the tag of the specified version as a string, preceded by "tags/".
    """

    if version_desired is None:
        # we should only update one step at a time.
        from pioreactor.version import __version__ as software_version

        version_history = get_non_prerelease_tags_of_pioreactor(repo)

        if software_version in version_history:
            ix = version_history.index(software_version)

            if ix >= 1:
                tag = f"tags/{version_history[ix-1]}"  # update to the succeeding version.
            elif ix == 0:
                tag = "latest"  # essentially a re-install?

        else:
            tag = "latest"

    elif version_desired == "latest":
        tag = "latest"
    else:
        tag = f"tags/{version_desired}"

    return tag


@update.command(name="app")
@click.option("-b", "--branch", help="install from a branch on github")
@click.option(
    "-r",
    "--repo",
    help="install from a repo on github. Format: 'username/project'",
    default="pioreactor/pioreactor",
)
@click.option("--source", help="use a URL, whl file, or release-***.zip file")
@click.option("-v", "--version", help="install a specific version, default is latest")
def update_app(
    branch: Optional[str],
    repo: str,
    source: Optional[str],
    version: Optional[str],
) -> None:
    """
    Update the Pioreactor core software
    """
    logger = create_logger(
        "update-app", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT
    )

    commands_and_priority: list[tuple[str, int]] = []

    if source is not None:
        import re

        if re.search("release_(.*).zip", source):
            version_installed = re.search("release_(.*).zip", source).groups()[0]  # type: ignore
            tmp_release_folder = f"/tmp/release_{version_installed}"
            commands_and_priority.extend(
                [
                    (f"rm -rf {tmp_release_folder}", -3),
                    (f"unzip {source} -d {tmp_release_folder}", -2),
                    (
                        f"unzip {tmp_release_folder}/wheels_{version_installed}.zip -d {tmp_release_folder}/wheels",
                        0,
                    ),
                    (f"sudo bash {tmp_release_folder}/pre_update.sh || true", 1),
                    (
                        f"sudo pip install --force-reinstall --no-index --find-links={tmp_release_folder}/wheels/ {tmp_release_folder}/pioreactor-{version_installed}-py3-none-any.whl",
                        2,
                    ),
                    (f"sudo bash {tmp_release_folder}/update.sh || true", 3),
                    (
                        f'sudo sqlite3 {config["storage"]["database"]} < {tmp_release_folder}/update.sql || true',
                        4,
                    ),
                    (f"sudo bash {tmp_release_folder}/post_update.sh || true", 5),
                ]
            )

        else:
            version_installed = source
            commands_and_priority.append(
                (f"sudo pip3 install --force-reinstall --no-index {source}", 1)
            )

    elif branch is not None:
        version_installed = quote(branch)
        commands_and_priority.append(
            (
                f"sudo pip3 install -U --force-reinstall https://github.com/{repo}/archive/{branch}.zip",
                1,
            )
        )

    else:
        tag = get_tag_to_install(repo, version)
        response = get(f"https://api.github.com/repos/{repo}/releases/{tag}")
        if response.raise_for_status():
            logger.error(f"Version {version} not found")
            raise click.Abort()

        release_metadata = loads(response.body)
        version_installed = release_metadata["tag_name"]
        for asset in release_metadata["assets"]:
            # add the following files to the release. They should ideally be idempotent!

            # pre_update.sh runs (if exists)
            # `pip install pioreactor...whl` runs
            # update.sh runs (if exists)
            # update.sql to update sqlite schema runs (if exists)
            # post_update.sh runs (if exists)

            # TODO: potential supply chain attack is to add malicious assets to releases
            url = asset["browser_download_url"]
            asset_name = asset["name"]

            if asset_name == "pre_update.sh":
                commands_and_priority.extend(
                    [
                        (f"wget -O /tmp/pre_update.sh {url}", 0),
                        ("sudo bash /tmp/pre_update.sh", 1),
                    ]
                )
            elif asset_name.startswith("pioreactor") and asset_name.endswith(".whl"):
                assert (
                    version_installed in url
                ), f"Hm, pip installing {url} but this doesn't match version specified for installing: {version_installed}"
                commands_and_priority.extend([(f'sudo pip3 install "pioreactor @ {url}"', 2)])
            elif asset_name == "update.sh":
                commands_and_priority.extend(
                    [
                        (f"wget -O /tmp/update.sh {url}", 3),
                        ("sudo bash /tmp/update.sh", 4),
                    ]
                )
            elif asset_name == "update.sql":
                commands_and_priority.extend(
                    [
                        (f"wget -O /tmp/update.sql {url}", 5),
                        (f'sudo sqlite3 {config["storage"]["database"]} < /tmp/update.sql', 6),
                    ]
                )
            elif asset_name == "post_update.sh":
                commands_and_priority.extend(
                    [
                        (f"wget -O /tmp/post_update.sh {url}", 99),
                        ("sudo bash /tmp/post_update.sh", 100),
                    ]
                )

    for command, _ in sorted(commands_and_priority, key=lambda t: t[1]):
        logger.debug(command)
        p = subprocess.run(
            command,
            shell=True,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if p.returncode != 0:
            logger.debug(p.stderr)
            logger.error("Update failed. See logs.")
            # end early
            raise click.Abort()
        else:
            logger.debug(p.stdout)

    logger.notice(f"Updated {whoami.get_unit_name()} to version {version_installed}.")  # type: ignore


@update.command(name="firmware")
@click.option("-v", "--version", help="install a specific version, default is latest")
def update_firmware(version: Optional[str]) -> None:
    """
    Update the RP2040 firmware
    """
    logger = create_logger(
        "update-app", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT
    )
    commands_and_priority: list[tuple[str, int]] = []

    if version is None:
        version = "latest"
    else:
        version = f"tags/{version}"

    release_metadata = loads(
        get(f"https://api.github.com/repos/pioreactor/pico-build/releases/{version}").body
    )
    version_installed = release_metadata["tag_name"]

    for asset in release_metadata["assets"]:
        url = asset["browser_download_url"]
        asset_name = asset["name"]

        if asset_name == "main.elf":
            commands_and_priority.extend(
                [
                    (f"sudo wget -O /usr/local/bin/main.elf {url}", 0),
                    ("sudo bash /usr/local/bin/load_rp2040.sh", 1),
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
            raise click.Abort()

    logger.notice(f"Updated Pioreactor firmware to version {version_installed}.")  # type: ignore


pio.add_command(plugin_management.click_install_plugin)
pio.add_command(plugin_management.click_uninstall_plugin)
pio.add_command(plugin_management.click_list_plugins)

# this runs on both leader and workers
run.add_command(jobs.monitor.click_monitor)


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
    run.add_command(jobs.mqtt_to_db_streaming.click_mqtt_to_db_streaming)
    run.add_command(jobs.watchdog.click_watchdog)
    run.add_command(actions.export_experiment_data.click_export_experiment_data)
    run.add_command(actions.backup_database.click_backup_database)
    run.add_command(actions.experiment_profile.click_experiment_profile)

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
    @click.option("--password", "-p", default="raspberry")
    def add_pioreactor(hostname: str, password: str) -> None:
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
            ["bash", "/usr/local/bin/add_new_pioreactor_worker_from_leader.sh", hostname, password],
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
    @click.option(
        "-t",
        "--terminate",
        is_flag=True,
        help="Terminate after dumping a more or less complete list",
    )
    def discover_workers(terminate: bool) -> None:
        from pioreactor.utils.networking import discover_workers_on_network

        for hostname in discover_workers_on_network(terminate):
            click.echo(hostname)

    @pio.command(name="cluster-status", short_help="report information on the cluster")
    def cluster_status() -> None:
        """
        Note that this only looks at the current cluster as defined in config.ini.
        """
        import socket

        def get_metadata(hostname):
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

            # get version
            result = pubsub.subscribe(
                f"pioreactor/{hostname}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/versions",
                timeout=1,
                name="CLI",
            )
            if result:
                versions = loads(result.payload.decode())
            else:
                versions = {"hat": "unknown", "hat_serial": "unknown"}

            # is reachable?
            reachable = networking.is_reachable(add_local(hostname))

            return ip, state, reachable, versions

        def display_data_for(hostname_status: tuple[str, str]) -> bool:
            hostname, status = hostname_status

            ip, state, reachable, versions = get_metadata(hostname)

            statef = click.style(
                f"{state:15s}", fg="green" if state in ("ready", "init") else "red"
            )
            ipf = f"{ip if (ip is not None) else 'unknown':20s}"

            is_leaderf = f"{('Y' if hostname==get_leader_hostname() else 'N'):15s}"
            hostnamef = f"{hostname:20s}"
            reachablef = f"{(click.style('Y', fg='green') if reachable       else click.style('N', fg='red')):23s}"
            statusf = f"{(click.style('Y', fg='green') if (status == '1') else click.style('N', fg='red')):23s}"
            versionf = f"{versions['hat']:15s}"

            click.echo(f"{hostnamef} {is_leaderf} {ipf} {statef} {reachablef} {statusf} {versionf}")
            return reachable & (state == "ready")

        worker_statuses = list(config["cluster.inventory"].items())
        n_workers = len(worker_statuses)

        click.secho(
            f"{'Unit / hostname':20s} {'Is leader?':15s} {'IP address':20s} {'State':15s} {'Reachable?':14s} {'Active?':14s} {'HAT version':15s}",
            bold=True,
        )
        if n_workers == 0:
            return

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            results = executor.map(display_data_for, worker_statuses)

        if not all(results):
            exit(1)

    @update.command(name="ui")
    @click.option("-b", "--branch", help="install from a branch on github")
    @click.option(
        "-r",
        "--repo",
        help="install from a repo on github. Format: username/project",
        default="pioreactor/pioreactorui",
    )
    @click.option("--source", help="use a tar.gz file")
    @click.option("-v", "--version", help="install a specific version")
    def update_ui(
        branch: Optional[str], repo: str, source: Optional[str], version: Optional[str]
    ) -> None:
        """
        Update the PioreactorUI

        Source, if provided, should be a .tar.gz with a top-level dir like pioreactorui-{version}/
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
            assert version is not None, "version must be provided with the -v option"
            version_installed = version

        elif branch is not None:
            version_installed = quote(branch)
            url = f"https://github.com/{repo}/archive/{branch}.tar.gz"
            source = "/tmp/pioreactorui.tar.gz"
            commands.append(["wget", url, "-O", source])

        else:
            latest_release_metadata = loads(
                get(f"https://api.github.com/repos/{repo}/releases/{version}").body
            )
            version_installed = latest_release_metadata["tag_name"]
            url = f"https://github.com/{repo}/archive/refs/tags/{version_installed}.tar.gz"
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


if __name__ == "__main__":
    pio()
