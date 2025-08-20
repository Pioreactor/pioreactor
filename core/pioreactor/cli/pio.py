# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
from os import geteuid
from shlex import quote
from typing import Optional

import click
import pioreactor
from msgspec.json import decode as loads
from msgspec.json import encode as dumps
from pioreactor import exc
from pioreactor import plugin_management
from pioreactor import whoami
from pioreactor.cli.lazy_group import LazyGroup
from pioreactor.config import config
from pioreactor.logging import create_logger
from pioreactor.mureq import get
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import get_from
from pioreactor.pubsub import post_into_leader
from pioreactor.utils import JobManager
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.networking import is_using_local_access_point
from pioreactor.utils.timing import current_utc_timestamp

lazy_subcommands = {
    "run": "pioreactor.cli.run.run",
    "plugins": "pioreactor.cli.plugins.plugins",
    "calibrations": "pioreactor.cli.calibrations.calibration",
}

if whoami.am_I_leader():
    # add in ability to control workers
    lazy_subcommands["workers"] = "pioreactor.cli.workers.workers"


def _build_commands_for_release_zip(
    version_installed: str,
    tmp_rls_dir: str,
    *,
    source_zip: Optional[str] = None,
    download_url: Optional[str] = None,
) -> list[tuple[str, float]]:
    """Return unified shell commands for updating from a release zip.

    Provide either a local `source_zip` path or a `download_url` to fetch.
    The ordering mirrors the existing local-zip path; execution is sorted by priority later.
    """
    import tempfile

    assert (source_zip is None) ^ (download_url is None), "Provide either source_zip or download_url"

    commands: list[tuple[str, float]] = []
    tmp_dir = tempfile.gettempdir()

    commands.append((f"sudo rm -rf {tmp_rls_dir}", -99))

    if download_url is not None:
        release_zip = os.path.join(tmp_dir, f"release_{version_installed}.zip")
        commands.append((f"wget -O {release_zip} {download_url}", -50))
        commands.append((f"unzip -o {release_zip} -d {tmp_rls_dir}", 0))
    else:
        assert source_zip is not None
        commands.append((f"unzip -o {source_zip} -d {tmp_rls_dir}", 0))

    commands.extend(
        [
            (f"unzip -o {tmp_rls_dir}/wheels_{version_installed}.zip -d {tmp_rls_dir}/wheels", 1),
            (f"sudo bash {tmp_rls_dir}/pre_update.sh", 2),
            (f"sudo bash {tmp_rls_dir}/update.sh", 4),
            (f"sudo bash {tmp_rls_dir}/post_update.sh", 20),
            (
                f'echo "moving {tmp_rls_dir}/pioreactorui_*.tar.gz to {tmp_dir}/pioreactorui_archive.tar.gz"',
                97,
            ),
            (f"mv {tmp_rls_dir}/pioreactorui_*.tar.gz {tmp_dir}/pioreactorui_archive.tar.gz", 98),
            (f"sudo rm -rf {tmp_rls_dir}", 99),
        ]
    )

    if whoami.am_I_leader():
        commands.extend(
            [
                (
                    f"sudo pip install --no-index --find-links={tmp_rls_dir}/wheels/ "
                    f"{tmp_rls_dir}/pioreactor-{version_installed}-py3-none-any.whl[leader,worker]",
                    3,
                ),
                (
                    f'sudo sqlite3 {config.get("storage","database")} < {tmp_rls_dir}/update.sql || :',
                    10,
                ),
            ]
        )
    else:
        commands.append(
            (
                f"sudo pip install --no-index --find-links={tmp_rls_dir}/wheels/ "
                f"{tmp_rls_dir}/pioreactor-{version_installed}-py3-none-any.whl[worker]",
                3,
            )
        )

    return commands


def get_update_app_commands(
    branch: Optional[str], repo: str, source: Optional[str], version: Optional[str]
) -> tuple[list[tuple[str, float]], str]:
    """Build the commands_and_priority list and return the installed version."""
    import tempfile
    import re

    commands_and_priority: list[tuple[str, float]] = []
    # source overrides branch/version
    if source is not None:
        source = quote(source)
        if re.search(r"release_\d{0,2}\.\d{0,2}\.\d{0,2}\w{0,6}\.zip$", source):
            # provided a release archive
            version_installed = re.search(r"release_(.*).zip$", source).groups()[0]  # type: ignore
            tmp_dir = tempfile.gettempdir()
            tmp_rls_dir = f"{tmp_dir}/release_{version_installed}"
            commands_and_priority.extend(
                _build_commands_for_release_zip(version_installed, tmp_rls_dir, source_zip=source)
            )
        elif source.endswith(".whl"):
            version_installed = source
            commands_and_priority.append((f"sudo pip install --force-reinstall --no-index {source}", 1))
        else:
            click.echo("Not a valid source file. Should be either a whl or release archive.")
            sys.exit(1)

    elif branch is not None:
        cleaned_branch = quote(branch)
        cleaned_repo = quote(repo)
        version_installed = cleaned_branch
        commands_and_priority.append(
            (
                f"sudo pip install --force-reinstall "
                f'"git+https://github.com/{cleaned_repo}.git@{cleaned_branch}#egg=pioreactor&subdirectory=core"',
                1,
            )
        )

    else:
        from pioreactor.cli.pio import get_tag_to_install

        try:
            tag = get_tag_to_install(repo, version)
        except HTTPException:
            raise HTTPException(
                f"Unable to retrieve information over internet. Is the Pioreactor connected to the internet? "
                f"Local access point is {'active' if is_using_local_access_point() else 'inactive'}."
            )

        # Determine the tag to install and fetch its metadata to get the resolved tag name
        response = get(f"https://api.github.com/repos/{repo}/releases/{tag}")
        if not response.ok:
            raise HTTPException(f"Version {version} not found on GitHub")
        release_metadata = loads(response.body)
        version_installed = release_metadata["tag_name"]

        # Download the single release zip and perform the identical steps as local release zip path
        tmp_dir = tempfile.gettempdir()
        tmp_rls_dir = f"{tmp_dir}/release_{version_installed}"
        release_zip_url = (
            f"https://github.com/{repo}/releases/download/{version_installed}/release_{version_installed}.zip"
        )
        commands_and_priority.extend(
            _build_commands_for_release_zip(version_installed, tmp_rls_dir, download_url=release_zip_url)
        )

    return commands_and_priority, version_installed


@click.group(
    cls=LazyGroup,
    lazy_subcommands=lazy_subcommands,
    invoke_without_command=True,
)
@click.option(
    "--version", "show_version", is_flag=True, help="print the Pioreactor software version and exit"
)
@click.pass_context
def pio(ctx, show_version: bool) -> None:
    """
    Execute commands on this Pioreactor.

    Configuration available: /home/pioreactor/.pioreactor/config.ini

    See full documentation: https://docs.pioreactor.com/user-guide/cli

    Report errors or feedback: https://github.com/Pioreactor/pioreactor/issues
    """

    if show_version:
        ctx.invoke(version)
        ctx.exit()

    if not whoami.is_testing_env():
        # this check could go somewhere else. TODO This check won't execute if calling pioreactor from a script.
        if not whoami.check_firstboot_successful():
            raise SystemError(
                "/usr/local/bin/firstboot.sh found on disk. firstboot.sh likely failed. Try looking for errors in `sudo systemctl status firstboot.service`."
            )

        # running as root can cause problems as files created by the software are owned by root
        if geteuid() == 0:
            raise SystemError("Don't run as root!")

        # user-installs of pioreactor are not the norm and cause problems. This may change in the future.
        if pioreactor.__file__ != "/usr/local/lib/python3.11/dist-packages/pioreactor/__init__.py":
            raise SystemError("Pioreactor installed in a non-standard location. Please re-install.")

    # https://click.palletsprojects.com/en/8.1.x/commands/#group-invocation-without-command
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

    # load plugins
    plugin_management.get_plugins()


@pio.command(name="logs", short_help="show recent logs")
@click.option("-n", default=100, type=int)
@click.option(
    "-f",
    is_flag=True,
    help="follow the logs, like tail -f",
)
def logs(n: int, f: bool) -> None:
    """
    Tail & stream the logs from this unit to the terminal. CTRL-C to exit.
    """
    log_file = config.get("logging", "log_file", fallback="/var/log/pioreactor.log")
    ui_log_file = config.get("logging", "ui_log_file", fallback="/var/log/pioreactor.log")

    if whoami.am_I_leader():
        log_files = list(set([log_file, ui_log_file]))  # deduping
    else:
        log_files = [log_file]

    with subprocess.Popen(
        ["tail", "-qn", str(n), "-f" if f else ""] + log_files,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            click.echo(line.decode("utf8").rstrip("\n"))


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
        sys.exit(1)


@pio.command(name="blink", short_help="blink LED")
def blink() -> None:
    """
    monitor job is required to be running.
    """
    post_into_leader(f"/api/workers/{whoami.get_unit_name()}/blink")


@pio.command(name="kill", short_help="kill job(s)")
@click.option("--job-name", type=click.STRING)
@click.option("--experiment", type=click.STRING)
@click.option("--job-source", type=click.STRING)
@click.option("--job-id", type=click.INT)
@click.option("--all-jobs", is_flag=True, help="kill all Pioreactor jobs running")
def kill(
    job_name: str | None, experiment: str | None, job_source: str | None, job_id: int | None, all_jobs: bool
) -> None:
    """
    stop job(s).
    """
    if not (job_name or experiment or job_source or all_jobs or job_id):
        raise click.Abort("Provide an option to kill. See --help")

    with JobManager() as jm:
        count = jm.kill_jobs(
            all_jobs=all_jobs, job_name=job_name, experiment=experiment, job_source=job_source, job_id=job_id
        )
    click.echo(f"Killed {count} job{'s' if count != 1 else ''}.")


@pio.command(name="version", short_help="print the Pioreactor software version")
@click.option("--verbose", "-v", is_flag=True, help="show more system information")
def version(verbose: bool) -> None:
    from pioreactor.version import tuple_to_text
    from pioreactor.version import software_version_info

    if verbose:
        import platform
        from pioreactor.version import hardware_version_info
        from pioreactor.version import serial_number
        from pioreactor.version import get_firmware_version
        from pioreactor.version import rpi_version_info
        from pioreactor.whoami import get_pioreactor_model

        click.echo(f"Pioreactor app:         {tuple_to_text(software_version_info)}")
        click.echo(f"Pioreactor HAT:         {tuple_to_text(hardware_version_info)}")
        click.echo(f"Pioreactor firmware:    {tuple_to_text(get_firmware_version())}")
        click.echo(f"Bioreactor model name:  {get_pioreactor_model().display_name}")
        click.echo(f"HAT serial number:      {serial_number}")
        click.echo(f"Operating system:       {platform.platform()}")
        click.echo(f"Raspberry Pi:           {rpi_version_info}")
        click.echo(f"Image version:          {whoami.get_image_git_hash()}")
        try:
            result = get_from("localhost", "/unit_api/versions/ui")
            result.raise_for_status()
            ui_version = result.json()["version"]
        except Exception:
            ui_version = "<Failed to fetch>"

        click.echo(f"Pioreactor UI:          {ui_version}")
    else:
        click.echo(tuple_to_text(software_version_info))


@pio.group(short_help="manage the local caches")
def cache():
    pass


@cache.command(name="view", short_help="print out the contents of a cache")
@click.argument("cache")
def view_cache(cache: str) -> None:
    for cacher in [local_intermittent_storage, local_persistent_storage]:  # TODO: this sucks
        with cacher(cache) as c:
            for key in sorted(list(c.iterkeys())):
                click.echo(f"{click.style(key, bold=True)} = {c[key]}")


@cache.command(name="clear", short_help="clear out the contents of a cache")
@click.argument("cache")
@click.argument("key")
@click.option("--as-int", is_flag=True, help="evict after casting key to int, useful for gpio pins.")
def clear_cache(cache: str, key: str, as_int: bool) -> None:
    for cacher in [local_intermittent_storage, local_persistent_storage]:
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

    """
    from pioreactor.pubsub import publish

    unit = whoami.get_unit_name()
    exp = whoami.get_assigned_experiment_name(unit)

    extra_args = {ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)}

    assert len(extra_args) > 0

    for setting, value in extra_args.items():
        setting = setting.replace("-", "_")
        publish(f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value)


@pio.group(invoke_without_command=True)
@click.option("-s", "--source", help="use a URL, whl file, or release-***.zip file")
@click.option("-b", "--branch", help="specify a branch")
@click.pass_context
def update(ctx, source: Optional[str], branch: Optional[str]) -> None:
    """
    update software for the app and UI
    """
    if ctx.invoked_subcommand is None:
        # run update app and then update ui
        if source is not None:
            # Local source: consume provided release zip or wheel
            ctx.invoke(update_app, source=source)
            ctx.invoke(update_ui, source="/tmp/pioreactorui_archive.tar.gz")
        elif branch is not None:
            # Developer flow: install app and UI from a branch
            ctx.invoke(update_app, branch=branch)
            ctx.invoke(update_ui, branch=branch)
        else:
            # Internet release flow: fetch single release zip, then use bundled UI archive
            ctx.invoke(update_app)
            ctx.invoke(update_ui, source="/tmp/pioreactorui_archive.tar.gz")


def get_non_prerelease_tags_of_pioreactor(repo) -> list[str]:
    """
    Returns a list of all the tag names associated with non-prerelease releases, sorted in descending order
    """
    from packaging.version import Version

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

    return sorted(non_prerelease_tags, key=Version)


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
        from pioreactor.version import __version__
        from packaging.version import Version
        from bisect import bisect

        software_version = Version(Version(__version__).base_version)  # this removes and .devY or rcx
        version_history = get_non_prerelease_tags_of_pioreactor(repo)
        if bisect(version_history, software_version, key=Version) < len(version_history):
            ix = bisect(version_history, software_version, key=Version)
            if ix >= 1:
                tag = f"tags/{version_history[ix]}"
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
    # initialize logger and build commands based on input parameters
    logger = create_logger("update_app", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT)
    commands_and_priority, version_installed = get_update_app_commands(branch, repo, source, version)

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
            sys.exit(1)
        elif p.stdout:
            logger.debug(p.stdout)

    logger.notice(f"Updated Pioreactor app to version {version_installed}.")  # type: ignore
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
            sys.exit(1)

    logger.info(f"Updated Pioreactor firmware to version {version_installed}.")  # type: ignore


def get_update_ui_commands(
    branch: Optional[str], repo: str, source: Optional[str], version: Optional[str]
) -> tuple[list[list[str]], str]:
    """Build the shell command sequence and return (commands, installed_version) for updating the UI from the monorepo."""
    import tempfile

    if version is None:
        version_ref = "latest"
    else:
        version_ref = f"tags/{version}"

    if source:
        source = quote(source)
        version_installed = source
        commands: list[list[str]] = []
    else:
        if branch:
            cleaned_branch = quote(branch)
            version_installed = cleaned_branch
            archive_url = f"https://github.com/{quote(repo)}/archive/{cleaned_branch}.tar.gz"
        else:
            latest_meta = loads(get(f"https://api.github.com/repos/{repo}/releases/{version_ref}").body)
            version_installed = latest_meta["tag_name"]
            archive_url = f"https://github.com/{repo}/archive/refs/tags/{version_installed}.tar.gz"

        tmp_dir = tempfile.gettempdir()
        repo_name = repo.split("/")[-1]
        tmp_archive = os.path.join(tmp_dir, f"{repo_name}-{version_installed}.tar.gz")
        tmp_extract = os.path.join(tmp_dir, f"{repo_name}-{version_installed}")
        source = os.path.join(tmp_dir, "pioreactorui_archive.tar.gz")
        intermediate_folder = os.path.join(tmp_dir, f"pioreactorui-{version_installed}")
        commands = [
            ["rm", "-rf", tmp_extract],
            ["rm", "-rf", intermediate_folder],
            ["wget", archive_url, "-O", tmp_archive],
            ["mkdir", "-p", tmp_extract],
            ["tar", "-xzf", tmp_archive, "-C", tmp_dir],
            ["mkdir", "-p", intermediate_folder],
            ["cp", "-r", os.path.join(tmp_extract, "web", "."), intermediate_folder],
            ["tar", "czf", source, "-C", tmp_dir, f"pioreactorui-{version_installed}"],
        ]

    assert source
    commands.append(["bash", "/usr/local/bin/update_ui.sh", source])
    return commands, version_installed


@update.command(name="ui")
@click.option("-b", "--branch", help="install from a branch on github")
@click.option(
    "-r",
    "--repo",
    help="install from a repo on github. Format: username/project",
    default="pioreactor/pioreactor",
)
@click.option("--source", help="use a tar.gz file")
@click.option("-v", "--version", help="install a specific version")
def update_ui(branch: Optional[str], repo: str, source: Optional[str], version: Optional[str]) -> None:
    """
    Update the PioreactorUI

    Source, if provided, should be a .tar.gz with a top-level dir like pioreactorui-{version}/
    This is what is provided from Github releases.
    """
    logger = create_logger("update_ui", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT)
    commands, version_installed = get_update_ui_commands(branch, repo, source, version)

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

    logger.info(f"Updated PioreactorUI to version {version_installed}.")  # type: ignore


if whoami.am_I_leader():

    @pio.command(short_help="access the database's CLI")
    def db() -> None:
        import os

        os.system(f"sqlite3 {config.get('storage','database')} -column -header")

    @pio.command(short_help="tail MQTT")
    @click.option("--topic", "-t", default="pioreactor/#")
    def mqtt(topic: str) -> None:
        with subprocess.Popen(
            [
                "mosquitto_sub",
                "-v",
                "-t",
                topic,
                "-F",
                "%19.19I||%t||%p",
                "-u",
                "pioreactor",
                "-P",
                "raspberry",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as process:
            assert process.stdout is not None
            for line in process.stdout:
                timestamp, topic, value = line.decode("utf8").rstrip("\n").split("||")
                click.echo(
                    click.style(timestamp, fg="cyan")
                    + " | "
                    + click.style(topic, fg="bright_green")
                    + " | "
                    + click.style(value, fg="bright_yellow")
                )
