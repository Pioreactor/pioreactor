# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from os import geteuid
from shlex import quote
from typing import Any
from typing import Optional

import click
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
from pioreactor.pubsub import post_into_leader
from pioreactor.utils import get_running_pio_job_id
from pioreactor.utils import JobManager
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.networking import is_using_local_access_point
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.utils.timing import to_datetime

lazy_subcommands = {
    "run": "pioreactor.cli.run.run",
    "plugins": "pioreactor.cli.plugins.plugins",
    "calibrations": "pioreactor.cli.calibrations.calibration",
}

if whoami.am_I_leader():
    # add in ability to control workers
    lazy_subcommands["workers"] = "pioreactor.cli.workers.workers"
    # experiment management is leader-only
    lazy_subcommands["experiments"] = "pioreactor.cli.experiments.experiments"


def get_update_app_commands(
    branch: Optional[str],
    repo: str,
    source: Optional[str],
    version: Optional[str],
    defer_web_restart: bool = False,
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
                [
                    (f"sudo rm -rf {tmp_rls_dir}", -99),
                    (f"unzip -o {source} -d {tmp_rls_dir}", 0),
                    (
                        f"unzip -o {tmp_rls_dir}/wheels_{version_installed}.zip -d {tmp_rls_dir}/wheels",
                        1,
                    ),  # noqa: E501
                    (f"sudo bash {tmp_rls_dir}/pre_update.sh", 2),
                    (f"sudo bash {tmp_rls_dir}/update.sh", 4),
                    (f"sudo bash {tmp_rls_dir}/post_update.sh", 20),
                    (f"sudo rm -rf {tmp_rls_dir}", 98),
                ]
            )
            if not defer_web_restart:
                commands_and_priority.append(
                    ("sudo systemctl restart pioreactor-web.target", 99)
                )  # restart lighttpd (flask api) and huey.
            if whoami.am_I_leader():
                commands_and_priority.extend(
                    [
                        (
                            f"/opt/pioreactor/venv/bin/pip install --no-index --find-links={tmp_rls_dir}/wheels/ {tmp_rls_dir}/pioreactor-{version_installed}-py3-none-any.whl[leader,worker]",
                            3,
                        ),  # noqa: E501
                        (
                            f'sudo sqlite3 {config.get("storage","database")} < {tmp_rls_dir}/update.sql || :',
                            10,
                        ),  # noqa: E501
                    ]
                )
            else:
                commands_and_priority.append(
                    (
                        f"/opt/pioreactor/venv/bin/pip install --no-index --find-links={tmp_rls_dir}/wheels/ {tmp_rls_dir}/pioreactor-{version_installed}-py3-none-any.whl[worker]",
                        3,
                    )  # noqa: E501
                )
        elif source.endswith(".whl"):
            version_installed = source
            commands_and_priority.append(
                (f"/opt/pioreactor/venv/bin/pip install --force-reinstall --no-index {source}", 1)
            )
            if not defer_web_restart:
                commands_and_priority.append(("sudo systemctl restart pioreactor-web.target", 30))
        else:
            click.echo("Not a valid source file. Should be either a whl or release archive.")
            raise click.Abort()
    elif branch is not None:
        cleaned_branch = quote(branch)
        cleaned_repo = quote(repo)
        version_installed = cleaned_branch
        commands_and_priority.append(
            (
                f"/opt/pioreactor/venv/bin/pip install --force-reinstall --index-url https://piwheels.org/simple --extra-index-url https://pypi.org/simple "
                f'"pioreactor[leader_worker] @ git+https://github.com/{cleaned_repo}.git@{cleaned_branch}#subdirectory=core"',
                1,
            )  # noqa: E501
        )
        if not defer_web_restart:
            commands_and_priority.append(("sudo systemctl restart pioreactor-web.target", 30))  # noqa: E501

    else:
        try:
            tag = get_tag_to_install(repo, version)
        except HTTPException:
            raise HTTPException(
                f"Unable to retrieve information over internet. Is the Pioreactor connected to the internet? "
                f"Local access point is {'active' if is_using_local_access_point() else 'inactive'}."
            )
        response = get(f"https://api.github.com/repos/{repo}/releases/{tag}")
        if not response.ok:
            raise HTTPException(f"Version {version} not found on GitHub")
        release_metadata = loads(response.body)
        version_installed = release_metadata["tag_name"]
        found_whl = False
        tmp_dir = tempfile.gettempdir()
        tmp_rls_dir = f"{tmp_dir}/release_{version_installed}"
        commands_and_priority.append((f"mkdir {tmp_rls_dir}", -9))
        commands_and_priority.append((f"rm -rf {tmp_rls_dir}", -10))
        for asset in release_metadata["assets"]:
            url = asset["browser_download_url"]
            name = asset["name"]
            if name == "pre_update.sh":
                commands_and_priority.extend(
                    [
                        (f"wget -O {tmp_rls_dir}/pre_update.sh {url}", 0),
                        (f"sudo bash {tmp_rls_dir}/pre_update.sh", 1),
                    ]
                )
            elif name.startswith("pioreactor") and name.endswith(".whl"):
                found_whl = True
                assert (
                    version_installed in url
                ), f"pip installing {url} but doesn't match version {version_installed}"
                if whoami.am_I_leader():
                    commands_and_priority.append(
                        (f'/opt/pioreactor/venv/bin/pip install "pioreactor[worker,leader] @ {url}"', 2)
                    )
                else:
                    commands_and_priority.append(
                        (f'/opt/pioreactor/venv/bin/pip install "pioreactor[worker] @ {url}"', 2)
                    )
            elif name == "update.sh":
                commands_and_priority.extend(
                    [
                        (f"wget -O {tmp_rls_dir}/update.sh {url}", 3),
                        (f"sudo bash {tmp_rls_dir}/update.sh", 4),
                    ]
                )
            elif name == "update.sql" and whoami.am_I_leader():
                commands_and_priority.extend(
                    [
                        (f"wget -O {tmp_rls_dir}/update.sql {url}", 5),
                        (
                            f'sudo sqlite3 {config.get("storage","database")} < {tmp_rls_dir}/update.sql || :',
                            6,
                        ),
                    ]
                )
            elif name == "post_update.sh":
                commands_and_priority.extend(
                    [
                        (f"wget -O {tmp_rls_dir}/post_update.sh {url}", 99),
                        (f"sudo bash {tmp_rls_dir}/post_update.sh", 100),
                    ]
                )
            else:
                commands_and_priority.append((f"wget -O {tmp_rls_dir}/{name} {url}", -1))
        if not found_whl:
            raise FileNotFoundError(f"Could not find a whl in assets of {repo} release {tag}")
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
        ["tail", "-qn", str(n)] + (["-f"] if f else []) + log_files,
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
        raise click.Abort()


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


@pio.group(name="jobs", short_help="job-related commands")
def jobs():
    """Interact with Pioreactor jobs."""
    pass


def _format_job_history_line(
    job_id: int,
    job_name: str,
    experiment: str,
    job_source: str | None,
    unit: str,
    started_at: str,
    ended_at: str | None,
) -> str:
    job_source_display = job_source or "unknown"
    ended_at_display = ended_at or "still running"
    job_id_label = click.style(f"[job_id={job_id}]", fg="cyan")
    job_name_label = click.style(job_name, fg="green", bold=True)
    ended_at_label = (
        click.style(ended_at_display, fg="yellow", bold=True) if ended_at is None else ended_at_display
    )

    return (
        f"{job_id_label} {job_name_label} "
        f"(unit={unit}, experiment={experiment}, source={job_source_display}) "
        f"started_at={started_at} ended_at={ended_at_label}"
    )


@jobs.command(name="running", short_help="show status of running job(s)")
def job_running() -> None:

    with JobManager() as jm:
        jobs = jm.list_jobs(
            all_jobs=True,
        )

    for job_name, _pid, found_job_id, *_ in jobs:
        job_id_label = click.style(f"[job_id={found_job_id}]", fg="cyan")
        job_name_label = click.style(job_name, fg="green", bold=True)
        click.echo(f"{job_id_label} {job_name_label} is running.")


@jobs.command(name="history", short_help="list historical jobs with timing")
def job_history() -> None:
    with JobManager() as jm:
        jobs = jm.list_job_history()

    if not jobs:
        click.echo("No historical jobs recorded.")
        return

    for job in jobs:
        click.echo(_format_job_history_line(*job))


@jobs.command(name="info", short_help="show details for a job")
@click.option("--job-id", type=click.INT)
@click.option("--job-name", type=click.STRING)
def job_info(job_id: int | None, job_name: str | None) -> None:

    def _format_timestamp_to_seconds(timestamp: str) -> str:
        """
        Truncate timestamps like 2024-01-01T00:00:00.123456Z to second precision.
        """
        try:
            dt = to_datetime(timestamp)
        except ValueError:
            return timestamp

        return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if job_id is None and job_name is None:
        click.echo("Provide --job-id or --job-name.")
        return

    if job_id is None and job_name is not None:
        job_id = get_running_pio_job_id(job_name)
        if job_id is None:
            click.echo(f"No running job found with name {job_name}.")
            return

    assert job_id is not None

    with JobManager() as jm:
        job = jm.get_job_info(job_id)
        settings = jm.list_job_settings(job_id) if job else []

    if job is None:
        click.echo(f"No job found with job_id={job_id}.")
        return

    (
        found_job_id,
        job_name,
        experiment,
        job_source,
        unit,
        started_at,
        ended_at,
        is_running,
        leader,
        pid,
        is_long_running_job,
    ) = job

    click.echo(
        _format_job_history_line(found_job_id, job_name, experiment, job_source, unit, started_at, ended_at)
    )

    status_label = (
        click.style("running", fg="green", bold=True) if is_running else click.style("stopped", fg="red")
    )
    click.echo(
        f"status={status_label} leader={leader} pid={pid} " f"is_long_running_job={bool(is_long_running_job)}"
    )

    if not settings:
        return

    click.echo("published settings:")
    for setting, value, created_at, updated_at in settings:
        setting_label = click.style(setting, fg="cyan")
        created_at_display = _format_timestamp_to_seconds(created_at)
        updated_at_display = _format_timestamp_to_seconds(updated_at) if updated_at is not None else ""

        def _stringify(val: Any) -> str:
            if val is None:
                return "None"
            if isinstance(val, bytes):
                try:
                    return val.decode()
                except Exception:
                    return str(val)
            return str(val)

        click.echo(
            f"  {setting_label}={_stringify(value)} "
            f"(created_at={created_at_display}, updated_at={updated_at_display})"
        )


@jobs.command(name="remove", short_help="remove a job record")
@click.option("--job-id", type=click.INT)
@click.option("--job-name", type=click.STRING)
def job_remove(job_id: int | None, job_name: str | None) -> None:
    if job_id is None and job_name is None:
        click.echo("Provide --job-id or --job-name.")
        return

    if job_id is None and job_name is not None:
        job_id = get_running_pio_job_id(job_name)
        if job_id is None:
            click.echo(f"No running job found with name {job_name}.")
            return

    assert job_id is not None

    with JobManager() as jm:
        job = jm.get_job_info(job_id)

        if job is None:
            click.echo(f"No job found with job_id={job_id}.")
            return

        is_running = bool(job[7])
        if is_running:
            click.echo("Job is still running. Stop it before removing the record.")
            return

        removed = jm.remove_job(job_id)

    if removed:
        click.echo(f"Removed job record {job_id}.")
    else:
        click.echo(f"Failed to remove job record {job_id}.")


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

        try:
            model = get_pioreactor_model().display_name
        except exc.NoModelAssignedError:
            model = ""

        click.echo(f"Pioreactor app:         {tuple_to_text(software_version_info)}")

        if whoami.am_I_a_worker():
            click.echo(f"Pioreactor HAT:         {tuple_to_text(hardware_version_info)}")
            click.echo(f"Pioreactor firmware:    {tuple_to_text(get_firmware_version())}")
            click.echo(f"Bioreactor model name:  {model}")
            click.echo(f"HAT serial number:      {serial_number}")

        click.echo(f"Operating system:       {platform.platform()}")
        click.echo(f"Raspberry Pi:           {rpi_version_info}")
        click.echo(f"Image version:          {whoami.get_image_git_hash()}")

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
    key_to_evict = int(key) if as_int else key
    removed = False

    for cacher in [local_intermittent_storage, local_persistent_storage]:
        with cacher(cache) as c:
            if key_to_evict in c:
                del c[key_to_evict]
                removed = True

    if removed:
        click.echo(f"Removed key {key_to_evict} from cache '{cache}'.")
    else:
        click.echo(f"No entry for key {key_to_evict} found in cache '{cache}'.")


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
    update software for the app (it's an alias for pio update app)
    """
    if ctx.invoked_subcommand is None:
        # run update app
        if source is not None:
            ctx.invoke(update_app, source=source)
        else:
            ctx.invoke(update_app, branch=branch)


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
@click.option(
    "--defer-web-restart",
    is_flag=True,
    default=False,
    help="skip restarting pioreactor-web.target; useful when another process will restart it later",
)
def update_app(
    branch: Optional[str],
    repo: str,
    source: Optional[str],
    version: Optional[str],
    defer_web_restart: bool = False,
) -> None:
    """
    Update the Pioreactor core software
    """
    # initialize logger and build commands based on input parameters
    logger = create_logger("update_app", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT)
    commands_and_priority, version_installed = get_update_app_commands(
        branch, repo, source, version, defer_web_restart=defer_web_restart
    )

    for command, _ in sorted(commands_and_priority, key=lambda t: t[1]):
        if whoami.is_testing_env():
            logger.debug(f"DRY-RUN: {command}")
            continue

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
            raise click.Abort()

    logger.info(f"Updated Pioreactor firmware to version {version_installed}.")  # type: ignore


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
