# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring --ignore-rpm
> pio logs
"""
from __future__ import annotations

from os import geteuid
from shlex import quote
from time import sleep
from typing import Optional

import click
from msgspec.json import decode as loads
from msgspec.json import encode as dumps

import pioreactor
from pioreactor import config
from pioreactor import exc
from pioreactor import whoami
from pioreactor.cli.lazy_group import LazyGroup
from pioreactor.logging import create_logger
from pioreactor.mureq import get
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import get_from_leader
from pioreactor.utils import JobManager
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.networking import is_using_local_access_point
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import am_I_leader

lazy_subcommands = {
    "run": "pioreactor.cli.run.run",
    "plugins": "pioreactor.cli.plugins.plugins",
}

if am_I_leader():
    # add in ability to control workers
    lazy_subcommands["workers"] = "pioreactor.cli.workers.workers"


@click.group(
    cls=LazyGroup,
    lazy_subcommands=lazy_subcommands,
    invoke_without_command=True,
)
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
    if not whoami.check_firstboot_successful():
        raise SystemError(
            "/usr/local/bin/firstboot.sh found on disk. firstboot.sh likely failed. Try looking for errors in `sudo systemctl status firstboot.service`."
        )

    if geteuid() == 0:
        raise SystemError("Don't run as root!")


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

    for line in follow(config.config["logging"]["log_file"]):
        click.echo(line, nl=False)


@pio.command(name="log", short_help="logs a message from the CLI")
@click.option("-m", "--message", required=True, type=str, help="the message to append to the log")
@click.option(
    "-l",
    "--level",
    default="debug",
    type=click.Choice(["debug", "info", "notice", "warning", "error", "critical"], case_sensitive=False),
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
    """
    monitor job is required to be running.
    """
    from pioreactor.pubsub import publish

    publish(
        f"pioreactor/{whoami.get_unit_name()}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/flicker_led_response_okay",
        1,
    )


@pio.command(name="kill", short_help="kill job(s)")
@click.option("--name", type=click.STRING)
@click.option("--experiment", type=click.STRING)
@click.option("--job-source", type=click.STRING)
@click.option("--all-jobs", is_flag=True, help="kill all Pioreactor jobs running")
def kill(name: str | None, experiment: str | None, job_source: str | None, all_jobs: bool) -> None:
    """
    stop job(s).
    """
    if not (name or experiment or job_source or all_jobs):
        raise click.Abort("Provide an option to kill.")
    with JobManager() as jm:
        count = jm.kill_jobs(all_jobs=all_jobs, name=name, experiment=experiment, job_source=job_source)
    click.echo(f"Killed {count} job{'s' if count != 1 else ''}.")


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
        from pioreactor.version import rpi_version_info
        from pioreactor.whoami import get_pioreactor_model_and_version

        click.echo(f"Pioreactor software:    {tuple_to_text(software_version_info)}")
        click.echo(f"Pioreactor HAT:         {tuple_to_text(hardware_version_info)}")
        click.echo(f"Pioreactor firmware:    {tuple_to_text(get_firmware_version())}")
        click.echo(f"Model name:             {get_pioreactor_model_and_version()}")
        click.echo(f"HAT serial number:      {serial_number}")
        click.echo(f"Operating system:       {platform.platform()}")
        click.echo(f"Raspberry Pi:           {rpi_version_info}")
        click.echo(f"Image version:          {whoami.get_image_git_hash()}")
        if whoami.am_I_leader():
            try:
                result = get_from_leader("api/versions/ui")
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
        "/home/pioreactor/.pioreactor/storage/" if not whoami.is_testing_env() else ".pioreactor/storage"
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
@click.option("--as-int", is_flag=True, help="evict after casting key to int, useful for gpio pins.")
def clear_cache(cache: str, key: str, as_int: bool) -> None:
    import os.path
    import tempfile

    tmp_dir = tempfile.gettempdir()

    persistant_dir = (
        "/home/pioreactor/.pioreactor/storage/" if not whoami.is_testing_env() else ".pioreactor/storage"
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
        if as_int:
            key = int(key)  # type: ignore

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
    from pioreactor.pubsub import publish

    unit = whoami.get_unit_name()
    exp = whoami.get_assigned_experiment_name(unit)

    extra_args = {ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)}

    assert len(extra_args) > 0

    for setting, value in extra_args.items():
        setting = setting.replace("-", "_")
        publish(f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value)


@pio.group()
def update() -> None:
    """
    update software for the app and UI
    """
    pass


def get_non_prerelease_tags_of_pioreactor(repo) -> list[str]:
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
    import subprocess

    logger = create_logger("update_app", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT)

    commands_and_priority: list[tuple[str, float]] = []

    if source is not None:
        source = quote(source)
        import re
        import tempfile

        if re.search(r"release_\d{0,2}\.\d{0,2}\.\d{0,2}\w{0,6}\.zip$", source):
            # provided a release archive
            version_installed = re.search(r"release_(.*).zip$", source).groups()[0]  # type: ignore
            tmp_dir = tempfile.gettempdir()
            tmp_rlse_dir = f"{tmp_dir}/release_{version_installed}"
            # fmt: off
            commands_and_priority.extend(
                [
                    (f"rm -rf {tmp_rlse_dir}", -99),
                    (f"unzip {source} -d {tmp_rlse_dir}", 0),
                    (f"unzip {tmp_rlse_dir}/wheels_{version_installed}.zip -d {tmp_rlse_dir}/wheels", 1),
                    (f"sudo bash {tmp_rlse_dir}/pre_update.sh", 2),
                    (f"sudo bash {tmp_rlse_dir}/update.sh", 4),
                    (f"sudo bash {tmp_rlse_dir}/post_update.sh", 20),
                    (f"rm -rf {tmp_rlse_dir}", 99),
                ]
            )

            if whoami.am_I_leader():
                commands_and_priority.extend([
                    (f"sudo pip install --no-index --find-links={tmp_rlse_dir}/wheels/ {tmp_rlse_dir}/pioreactor-{version_installed}-py3-none-any.whl[leader,worker]", 3),
                    (f'sudo sqlite3 {config.config["storage"]["database"]} < {tmp_rlse_dir}/update.sql', 10),
                    (f"mv {tmp_rlse_dir}/pioreactorui_*.tar.gz {tmp_dir}/pioreactorui_archive", 98),  # move ui folder to be accessed by a `pio update ui`
                ])
            else:
                commands_and_priority.extend([
                    (f"sudo pip install --no-index --find-links={tmp_rlse_dir}/wheels/ {tmp_rlse_dir}/pioreactor-{version_installed}-py3-none-any.whl[worker]", 3),
                ])

            # fmt: on
        elif source.endswith(".whl"):
            # provided a whl
            version_installed = source
            commands_and_priority.append((f"sudo pip3 install --force-reinstall --no-index {source}", 1))
        else:
            click.echo("Not a valid source file. Should be either a whl or release archive.")
            raise click.Abort()

    elif branch is not None:
        cleaned_branch = quote(branch)
        cleaned_repo = quote(repo)
        version_installed = cleaned_branch
        commands_and_priority.append(
            (f"sudo pip3 install --force-reinstall https://github.com/{cleaned_repo}/archive/{cleaned_branch}.zip", 1,)  # fmt: skip
        )

    else:
        try:
            tag = get_tag_to_install(repo, version)
        except HTTPException:
            raise HTTPException(
                f"Unable to retrieve information over internet. Is the Pioreactor connected to the internet? Local access point is {'active' if is_using_local_access_point() else 'inactive'}."
            )
        response = get(f"https://api.github.com/repos/{repo}/releases/{tag}")
        if response.raise_for_status():
            logger.error(f"Version {version} not found")
            raise click.Abort()

        release_metadata = loads(response.body)
        version_installed = release_metadata["tag_name"]
        found_whl = False

        # nuke all existing assets in /tmp
        # TODO: just make a new tempdir, put all files there, and then nuke that temp dir......
        # BETTER TODO: just download the release archive and run the script above.....
        commands_and_priority.append(("rm -f /tmp/*update.sh /tmp/update.sql", -1))

        for asset in release_metadata["assets"]:
            # add the following files to the release. They should ideally be idempotent!

            # pre_update.sh runs (if exists)
            # `pip install pioreactor...whl` runs
            # update.sh runs (if exists)
            # update.sql to update sqlite schema runs (if exists)
            # post_update.sh runs (if exists)
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
                found_whl = True
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
            elif asset_name == "update.sql" and whoami.am_I_leader():
                commands_and_priority.extend(
                    [
                        (f"wget -O /tmp/update.sql {url}", 5),
                        (
                            f'sudo sqlite3 {config.config["storage"]["database"]} < /tmp/update.sql || :',
                            6,
                        ),  # or True at the end, since this may run on workers, that's okay.
                    ]
                )
            elif asset_name == "post_update.sh":
                commands_and_priority.extend(
                    [
                        (f"wget -O /tmp/post_update.sh {url}", 99),
                        ("sudo bash /tmp/post_update.sh", 100),
                    ]
                )
        if not found_whl:
            raise FileNotFoundError(f"Could not find a whl file in the {repo=} {tag=} release.")

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
    # everything work? Let's publish to MQTT. This is a terrible hack, as monitor should do this.
    from pioreactor.pubsub import publish

    publish(
        f"pioreactor/{whoami.get_unit_name()}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/versions/set",
        dumps({"app": version_installed, "timestamp": current_utc_timestamp()}),
    )


@update.command(name="firmware")
@click.option("-v", "--version", help="install a specific version, default is latest")
def update_firmware(version: Optional[str]) -> None:
    """
    Update the RP2040 firmware.

    # TODO: this needs accept a --source arg
    """
    import subprocess

    logger = create_logger(
        "update_firmware", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT
    )
    commands_and_priority: list[tuple[str, int]] = []

    if version is None:
        version = "latest"
    else:
        version = quote(version)
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


if whoami.am_I_leader():

    @pio.command(short_help="access the db CLI")
    def db() -> None:
        import os

        os.system(f"sqlite3 {config.config['storage']['database']} -column -header")

    @pio.command(short_help="tail MQTT")
    @click.option("--topic", "-t", default="pioreactor/#")
    def mqtt(topic: str) -> None:
        import os

        os.system(f"""mosquitto_sub -v -t '{topic}' -F "%19.19I  |  %t   %p" -u pioreactor -P raspberry""")

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
    def update_ui(branch: Optional[str], repo: str, source: Optional[str], version: Optional[str]) -> None:
        """
        Update the PioreactorUI

        Source, if provided, should be a .tar.gz with a top-level dir like pioreactorui-{version}/
        This is what is provided from Github releases.
        """
        import subprocess

        logger = create_logger(
            "update_ui", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT
        )
        commands = []

        if version is None:
            version = "latest"
        else:
            version = f"tags/{version}"

        if source is not None:
            source = quote(source)
            version_installed = source

        elif branch is not None:
            cleaned_branch = quote(branch)
            cleaned_repo = quote(repo)
            version_installed = cleaned_branch
            url = f"https://github.com/{cleaned_repo}/archive/{cleaned_branch}.tar.gz"
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
        commands.append(["bash", "/usr/local/bin/update_ui.sh", source])

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
                raise exc.BashScriptError(p.stderr)

        logger.notice(f"Updated PioreactorUI to version {version_installed}.")  # type: ignore
