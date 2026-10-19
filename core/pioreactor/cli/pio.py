# -*- coding: utf-8 -*-
import ast
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import typing as t
from contextlib import closing
from os import geteuid
from pathlib import Path
from shlex import join
from shlex import quote
from typing import Any
from uuid import uuid4

import click
from pioreactor import exc
from pioreactor import whoami
from pioreactor.cli import resume_garbage_collection
from pioreactor.cli.lazy_group import LazyGroup
from pioreactor.config import get_config
from pioreactor.config import set_config_value_in_file
from pioreactor.paths import get_dot_pioreactor_path
from pioreactor.paths import get_pio_venv_path

lazy_subcommands = {
    "run": "pioreactor.cli.run.run",
    "plugins": "pioreactor.cli.plugins.plugins",
    "calibrations": "pioreactor.cli.calibrations.calibration",
    "estimators": "pioreactor.cli.estimators.estimators",
    "usb": "pioreactor.cli.usb.usb",
    "model": "pioreactor.cli.model.model",
    "active": "pioreactor.cli.active.active",
    "cluster": "pioreactor.cli.cluster.cluster",
}

if whoami.am_I_leader():
    # add in ability to control workers
    lazy_subcommands["workers"] = "pioreactor.cli.workers.workers"
    # experiment management is leader-only
    lazy_subcommands["experiments"] = "pioreactor.cli.experiments.experiments"


GIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{4,40}$")
GITHUB_REPO_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
GIT_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
RELEASE_ARCHIVE_PATTERN = re.compile(r"release_\d{2}\.\d{1,2}\.\d+\w{0,6}\.zip$")
STAGED_RELEASE_ARCHIVE_PREFIX = "pioreactor_update_archive_"
LOCAL_PIO_EXECUTABLE = os.environ.get("PIO_EXECUTABLE", "pio")
UpdateCommand = tuple[list[str], float, bool]


def validate_git_sha(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned_value = value.strip()
    if not GIT_SHA_PATTERN.fullmatch(cleaned_value):
        raise click.BadParameter("Expected a commit SHA (4 to 40 hexadecimal characters).")

    return cleaned_value.lower()


def validate_git_sha_option(_ctx: click.Context, _param: click.Parameter, value: str | None) -> str | None:
    return validate_git_sha(value)


def validate_github_repo(value: str) -> str:
    cleaned_value = value.strip()
    if not GITHUB_REPO_PATTERN.fullmatch(cleaned_value):
        raise click.BadParameter("Expected a GitHub repo in owner/repo format.")

    return cleaned_value


def validate_github_repo_option(
    _ctx: click.Context, _param: click.Parameter, value: str | None
) -> str | None:
    if value is None:
        return None
    return validate_github_repo(value)


def validate_git_ref(value: str) -> str:
    cleaned_value = value.strip()
    if (
        not GIT_REF_PATTERN.fullmatch(cleaned_value)
        or ".." in cleaned_value
        or cleaned_value.endswith((".", "/"))
    ):
        raise click.BadParameter(
            "Expected a branch/ref without quotes, whitespace, control characters, or shell metacharacters."
        )

    return cleaned_value


def validate_git_ref_option(_ctx: click.Context, _param: click.Parameter, value: str | None) -> str | None:
    if value is None:
        return None
    return validate_git_ref(value)


def update_command(command: list[str], priority: float, allow_failure: bool = False) -> UpdateCommand:
    return command, priority, allow_failure


def build_staged_release_archive_location(release_filename: str) -> str:
    return str(
        Path(tempfile.gettempdir()) / f"{STAGED_RELEASE_ARCHIVE_PREFIX}{uuid4().hex}_{release_filename}"
    )


def get_dot_pioreactor_root() -> Path:
    return get_dot_pioreactor_path()


def require_repair_command_paths(*command_names: str) -> dict[str, str]:
    paths = {name: shutil.which(name) for name in command_names}
    missing_commands = [name for name, path in paths.items() if path is None]

    if missing_commands:
        available_commands = ", ".join(command_names[:-1]) + f", and {command_names[-1]}"
        raise click.ClickException(f"{available_commands} are required.")

    return {name: t.cast(str, path) for name, path in paths.items()}


def build_dot_pioreactor_repair_commands(dot_pioreactor_root: Path, tools: dict[str, str]) -> list[list[str]]:
    return [
        [
            tools["sudo"],
            tools["find"],
            str(dot_pioreactor_root),
            "-mindepth",
            "0",
            "(",
            "!",
            "-user",
            "pioreactor",
            "-o",
            "!",
            "-group",
            "www-data",
            ")",
            "-exec",
            tools["chown"],
            "-h",
            "pioreactor:www-data",
            "{}",
            "+",
        ],
        [tools["sudo"], tools["chmod"], "g+w", str(dot_pioreactor_root)],
        [
            tools["sudo"],
            tools["find"],
            str(dot_pioreactor_root),
            "-mindepth",
            "1",
            "(",
            "-type",
            "d",
            "-o",
            "-type",
            "f",
            ")",
            "-exec",
            tools["chmod"],
            "g+w",
            "{}",
            "+",
        ],
        [
            tools["sudo"],
            tools["find"],
            str(dot_pioreactor_root),
            "-type",
            "d",
            "!",
            "-perm",
            "-2000",
            "-exec",
            tools["chmod"],
            "g+s",
            "{}",
            "+",
        ],
    ]


def get_runtime_cache_database_paths(run_pioreactor_cache: Path) -> list[Path]:
    return [
        run_pioreactor_cache / "local_intermittent_pioreactor_metadata.sqlite",
        run_pioreactor_cache / "huey.db",
    ]


def build_runtime_repair_commands(tools: dict[str, str]) -> list[list[str]]:
    run_pioreactor_root = Path("/run/pioreactor")
    run_pioreactor_exports = run_pioreactor_root / "exports"
    run_pioreactor_cache = run_pioreactor_root / "cache"
    runtime_cache_databases = [str(path) for path in get_runtime_cache_database_paths(run_pioreactor_cache)]

    cache_sidecar_selector = [
        tools["sudo"],
        tools["find"],
        str(run_pioreactor_cache),
        "-maxdepth",
        "1",
        "-type",
        "f",
        "(",
        "-name",
        "*-wal",
        "-o",
        "-name",
        "*-shm",
        ")",
        "-exec",
    ]

    return [
        [
            tools["sudo"],
            tools["install"],
            "-d",
            "-o",
            "pioreactor",
            "-g",
            "www-data",
            "-m",
            "2775",
            str(run_pioreactor_root),
        ],
        [
            tools["sudo"],
            tools["install"],
            "-d",
            "-o",
            "pioreactor",
            "-g",
            "www-data",
            "-m",
            "2775",
            str(run_pioreactor_exports),
        ],
        [
            tools["sudo"],
            tools["find"],
            str(run_pioreactor_exports),
            "-maxdepth",
            "1",
            "-type",
            "f",
            "(",
            "(",
            "-name",
            "*.tmp",
            "-o",
            "-name",
            "*.csv",
            ")",
            "-mmin",
            "+30",
            "-o",
            "(",
            "-name",
            "export_*.zip",
            "-mmin",
            "+360",
            ")",
            ")",
            "-delete",
        ],
        [
            tools["sudo"],
            tools["install"],
            "-d",
            "-o",
            "pioreactor",
            "-g",
            "www-data",
            "-m",
            "2770",
            str(run_pioreactor_cache),
        ],
        [tools["sudo"], tools["touch"], *runtime_cache_databases],
        [
            tools["sudo"],
            tools["chown"],
            "-h",
            "pioreactor:www-data",
            *runtime_cache_databases,
        ],
        [tools["sudo"], tools["chmod"], "0660", *runtime_cache_databases],
        [
            *cache_sidecar_selector,
            tools["chown"],
            "-h",
            "pioreactor:www-data",
            "{}",
            "+",
        ],
        [
            *cache_sidecar_selector,
            tools["chmod"],
            "0660",
            "{}",
            "+",
        ],
    ]


def get_inactive_pioreactor_web_services(systemctl_path: str) -> list[str]:
    inactive_services: list[str] = []
    for service in ("lighttpd.service", "huey.service"):
        result = subprocess.run([systemctl_path, "is-active", "--quiet", service], check=False)
        if result.returncode != 0:
            inactive_services.append(service)

    return inactive_services


def restart_inactive_pioreactor_web_services(tools: dict[str, str]) -> list[str]:
    inactive_services = get_inactive_pioreactor_web_services(tools["systemctl"])
    for service in inactive_services:
        subprocess.run([tools["sudo"], tools["systemctl"], "restart", service], check=True)

    return inactive_services


def get_inactive_pioreactor_startup_run_services(systemctl_path: str) -> list[str]:
    job_names = ["monitor"]
    if whoami.am_I_leader():
        job_names.append("mqtt_to_db_streaming")

    inactive_services: list[str] = []
    for job_name in job_names:
        service = f"pioreactor_startup_run@{job_name}.service"
        result = subprocess.run([systemctl_path, "is-active", "--quiet", service], check=False)
        if result.returncode != 0:
            inactive_services.append(service)

    return inactive_services


def restart_inactive_pioreactor_startup_run_services(tools: dict[str, str]) -> list[str]:
    inactive_services = get_inactive_pioreactor_startup_run_services(tools["systemctl"])
    for service in inactive_services:
        subprocess.run([tools["sudo"], tools["systemctl"], "restart", service], check=True)

    return inactive_services


def get_update_app_commands(
    branch: str | None,
    repo: str,
    source: str | None,
    version: str | None,
    sha: str | None = None,
    no_deps: bool = False,
    defer_web_restart: bool = False,
) -> tuple[list[UpdateCommand], str]:
    """Build the commands_and_priority list and return the installed version."""
    import tempfile
    import re
    from msgspec.json import decode as loads
    from pioreactor.config import config
    from pioreactor.mureq import get
    from pioreactor.mureq import HTTPException
    from pioreactor.utils.networking import is_using_local_access_point

    pio_venv_bin = get_pio_venv_path() / "bin"

    def get_install_extra_for_this_unit() -> str:
        # The extra depends on whether this unit has Pioreactor hardware, not on its role. Use the
        # role-named extras: they exist in older releases too, so installing an older version still
        # pulls in its leader and hardware dependencies.
        has_hardware = not whoami.am_I_leader() or whoami.am_I_a_worker()
        return "leader_worker" if has_hardware else "leader"

    def create_commands_for_release_archive(
        archive_location: str, release_version: str
    ) -> list[UpdateCommand]:
        tmp_dir = tempfile.gettempdir()
        tmp_rls_dir = f"{tmp_dir}/release_{release_version}"
        # Current invariant: release updates require the configured storage
        # database; a missing [storage].database entry is invalid configuration.
        database_path = config.get("storage", "database")

        release_commands: list[UpdateCommand] = [
            update_command(
                [
                    LOCAL_PIO_EXECUTABLE,
                    "update",
                    "verify-release-archive",
                    archive_location,
                    "--expected-version",
                    release_version,
                ],
                -99.5,
            ),
            update_command(["sudo", "rm", "-rf", tmp_rls_dir], -99),
            update_command(["unzip", "-o", archive_location, "-d", tmp_rls_dir], 0),
            update_command(
                ["unzip", "-o", f"{tmp_rls_dir}/wheels_{release_version}.zip", "-d", f"{tmp_rls_dir}/wheels"],
                1,
            ),
            update_command(["sudo", "bash", f"{tmp_rls_dir}/pre_update.sh"], 2),
            update_command(["sudo", "bash", f"{tmp_rls_dir}/update.sh"], 4),
            update_command(["sudo", "bash", f"{tmp_rls_dir}/post_update.sh"], 20),
        ]

        release_commands.append(update_command(["sudo", "rm", "-rf", tmp_rls_dir], 98))

        if not defer_web_restart:
            release_commands.append(
                update_command(["sudo", "systemctl", "restart", "pioreactor-web.target"], 99)
            )

        install_extra = get_install_extra_for_this_unit()

        release_commands.append(
            update_command(
                [
                    str(pio_venv_bin / "pip"),
                    "install",
                    "--no-index",
                    f"--find-links={tmp_rls_dir}/wheels/",
                    f"{tmp_rls_dir}/pioreactor-{release_version}-py3-none-any.whl[{install_extra}]",
                ],
                3,
            )
        )

        release_commands.append(
            update_command(
                [
                    str(pio_venv_bin / "pio"),
                    "repair",
                ],
                99,
            )
        )

        if whoami.am_I_leader():
            release_commands.extend(
                [
                    update_command(
                        [
                            "sudo",
                            "sqlite3",
                            "-cmd",
                            ".timeout 15000",
                            database_path,
                            f".read {tmp_rls_dir}/update.sql",
                        ],
                        10,
                        allow_failure=True,
                    ),
                    update_command(
                        [
                            "sudo",
                            "sqlite3",
                            "-cmd",
                            ".timeout 15000",
                            database_path,
                            "PRAGMA optimize = 0x10002",
                        ],
                        11,
                        allow_failure=True,
                    ),
                ]
            )

        return release_commands

    commands_and_priority: list[UpdateCommand] = []
    sha = validate_git_sha(sha)
    repo = validate_github_repo(repo)
    # source overrides branch/version/sha
    if source is not None:
        # download production
        if RELEASE_ARCHIVE_PATTERN.search(source):
            # provided a release archive
            version_installed = re.search(r"release_(.*).zip$", source).groups()[0]  # type: ignore
            commands_and_priority.extend(create_commands_for_release_archive(source, version_installed))
        elif source.endswith(".whl"):
            version_installed = source
            commands_and_priority.append(
                update_command(
                    [
                        str(pio_venv_bin / "pip"),
                        "install",
                        "--force-reinstall",
                        "--no-index",
                        source,
                    ],
                    1,
                )
            )
            if not defer_web_restart:
                commands_and_priority.append(
                    update_command(["sudo", "systemctl", "restart", "pioreactor-web.target"], 30)
                )
        else:
            click.echo("Not a valid source file. Should be either a whl or release archive.")
            raise click.Abort()
    elif branch is not None or sha is not None:
        # download dev
        git_ref = branch if branch is not None else sha
        assert git_ref is not None
        cleaned_ref = validate_git_ref(git_ref)
        version_installed = cleaned_ref
        no_deps_args = ["--no-deps"] if no_deps else []
        install_extra = get_install_extra_for_this_unit()
        commands_and_priority.append(
            update_command(
                [
                    str(pio_venv_bin / "pip"),
                    "install",
                    "--force-reinstall",
                    *no_deps_args,
                    "--index-url",
                    "https://piwheels.org/simple",
                    "--extra-index-url",
                    "https://pypi.org/simple",
                    f"pioreactor[{install_extra}] @ git+https://github.com/{repo}.git@{cleaned_ref}#subdirectory=core",
                ],
                1,
            )  # noqa: E501
        )
        if not defer_web_restart:
            commands_and_priority.append(
                update_command(["sudo", "systemctl", "restart", "pioreactor-web.target"], 30)
            )

    else:
        # source is specified, likely in /tmp
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
        archive_name = f"release_{version_installed}.zip"
        archive_url = None
        for asset in release_metadata["assets"]:
            name = asset["name"]
            if name == archive_name:
                archive_url = asset["browser_download_url"]
                break

        if archive_url is None:
            raise FileNotFoundError(f"Could not find {archive_name} in assets of {repo} release {tag}")

        archive_location = build_staged_release_archive_location(archive_name)
        commands_and_priority.append(
            update_command(["wget", "-nv", "-O", archive_location, archive_url], -100)
        )
        commands_and_priority.extend(create_commands_for_release_archive(archive_location, version_installed))
        commands_and_priority.append(update_command(["sudo", "rm", "-f", archive_location], 97))
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
def pio(ctx: click.Context, show_version: bool) -> None:
    """
    Execute commands on this Pioreactor. See the "cluster" command `pios` too.

    Configuration available: /home/pioreactor/.pioreactor/config.ini

    See full documentation: https://docs.pioreactor.com/user-guide/cli

    Report errors or feedback: https://github.com/Pioreactor/pioreactor/issues
    """
    if ctx.invoked_subcommand != "run":
        # `pio run` resumes it after loading plugins, just before the job starts.
        resume_garbage_collection()

    if show_version:
        ctx.invoke(version)
        ctx.exit()

    if not whoami.is_testing_env():
        # This guards Click entrypoints; code that invokes jobs directly does not pass through pio startup.
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


def _resolve_config_paths_like_runtime() -> tuple[Path, Path]:
    """Resolve global and local config paths with runtime-like precedence."""
    from pioreactor.config import resolve_global_config_path
    from pioreactor.config import resolve_local_config_path

    return resolve_global_config_path(), resolve_local_config_path()


def _load_config_file(config_path: Path) -> t.Any:
    from pioreactor.config import ConfigParserMod

    parser = ConfigParserMod(strict=False)
    if config_path.is_file():
        parser.read([str(config_path)])
    return parser


def _format_config_key_value(option_name: str, option_value: str | None) -> str:
    return option_name if option_value is None else f"{option_name}={option_value}"


def _get_effective_config_value(section_name: str, parameter_name: str) -> str:
    from pioreactor.config import get_config

    effective_config = get_config()

    if not effective_config.has_section(section_name):
        raise click.ClickException(f"Section '{section_name}' not found in effective config.")

    if not effective_config.has_option(section_name, parameter_name):
        raise click.ClickException(f"Key '{parameter_name}' not found in section '{section_name}'.")

    return effective_config.get(section_name, parameter_name)


def _get_config_value_from_file(config_path: Path, section_name: str, parameter_name: str) -> str:
    config = _load_config_file(config_path)

    if not config.has_section(section_name):
        raise click.ClickException(f"Section '{section_name}' not found in config file.")

    if not config.has_option(section_name, parameter_name):
        raise click.ClickException(f"Key '{parameter_name}' not found in section '{section_name}'.")

    return config.get(section_name, parameter_name)


@pio.group(name="config", short_help="inspect effective configuration")
def config_group() -> None:
    """Show effective configuration values."""
    pass


@config_group.command(name="get", short_help="show one effective config value")
@click.argument(
    "section_name", type=click.STRING, help="Config section without brackets, e.g. stirring.config."
)
@click.argument(
    "parameter_name", type=click.STRING, help="Key within the section, e.g. target_rpm_outside_od_reading."
)
@click.option("--shared", is_flag=True, help="read from the shared config.ini only")
@click.option("--specific", is_flag=True, help="read from the unit-specific unit_config.ini only")
def get_config_value(section_name: str, parameter_name: str, shared: bool, specific: bool) -> None:
    if shared and specific:
        raise click.BadParameter("Specify at most one of --shared or --specific.")

    if not shared and not specific:
        click.echo(_get_effective_config_value(section_name, parameter_name))
        return

    global_config_path, local_config_path = _resolve_config_paths_like_runtime()
    selected_config_path = global_config_path if shared else local_config_path
    click.echo(_get_config_value_from_file(selected_config_path, section_name, parameter_name))


@config_group.command(name="set", short_help="set one config value")
@click.argument(
    "section_name", type=click.STRING, help="Config section without brackets, e.g. stirring.config."
)
@click.argument(
    "parameter_name", type=click.STRING, help="Key within the section, e.g. target_rpm_outside_od_reading."
)
@click.argument("value", type=click.STRING, help="Value to write, e.g. 500. Quote values containing spaces.")
@click.option("--shared", is_flag=True, help="write to the shared config.ini")
@click.option("--specific", is_flag=True, help="write to the unit-specific unit_config.ini")
def set_config_value(
    section_name: str,
    parameter_name: str,
    value: str,
    shared: bool,
    specific: bool,
) -> None:
    if shared == specific:
        raise click.BadParameter("Specify exactly one of --shared or --specific.")

    global_config_path, local_config_path = _resolve_config_paths_like_runtime()

    if shared:
        if not whoami.am_I_leader():
            return
        target_config_path = global_config_path
    else:
        target_config_path = local_config_path

    set_config_value_in_file(target_config_path, section_name, parameter_name, value)


@config_group.command(name="show", short_help="show the effective merged config")
@click.option("--section", "section_name", type=click.STRING, help="show only one section")
@click.option("--key", "key_name", type=click.STRING, help="show only one key (requires --section)")
@click.option("--json", "json_output", is_flag=True, help="output as json")
@click.option("--with-source", is_flag=True, help="include source: global/local/derived")
def show_config(
    section_name: str | None,
    key_name: str | None,
    json_output: bool,
    with_source: bool,
) -> None:
    """
    Print the merged config (global + local + derived sections).
    """
    from msgspec.json import encode as dumps
    from pioreactor.config import get_config

    if key_name is not None and section_name is None:
        raise click.BadParameter("--key requires --section.", param_hint="--key")

    global_config_path, local_config_path = _resolve_config_paths_like_runtime()
    global_config = _load_config_file(global_config_path)
    local_config = _load_config_file(local_config_path)

    def value_source(section: str, key: str) -> str:
        if local_config.has_section(section) and local_config.has_option(section, key):
            return "local"
        if global_config.has_section(section) and global_config.has_option(section, key):
            return "global"
        return "derived"

    effective_config = get_config()
    payload: dict[str, dict[str, str | None]] = {}
    for section in sorted(effective_config.sections()):
        payload[section] = {
            option_name: option_value
            for option_name, option_value in sorted(effective_config[section].items())
        }

    if section_name is not None:
        if section_name not in payload:
            raise click.ClickException(f"Section '{section_name}' not found in effective config.")
        payload = {section_name: payload[section_name]}

    if key_name is not None:
        assert section_name is not None
        if key_name not in payload[section_name]:
            raise click.ClickException(f"Key '{key_name}' not found in section '{section_name}'.")
        payload = {section_name: {key_name: payload[section_name][key_name]}}

    if json_output:
        if with_source:
            payload_with_source = {
                section: {
                    key: {"value": value, "source": value_source(section, key)}
                    for key, value in options.items()
                }
                for section, options in payload.items()
            }
            click.echo(dumps(payload_with_source).decode())
            return

        click.echo(dumps(payload).decode())
        return

    sections = list(payload.items())
    for section_index, (section, options) in enumerate(sections):
        click.echo(f"[{section}]")
        for key, value in options.items():
            line = _format_config_key_value(key, value)
            if with_source:
                line = f"{line}  # source={value_source(section, key)}"
            click.echo(line)

        if section_index < len(sections) - 1:
            click.echo("")


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
    from pioreactor.config import config

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
        text=True,
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            click.echo(line.rstrip("\n"))


@pio.command(name="log", short_help="append a log message from the CLI")
@click.option("-m", "--message", required=True, type=str, help="the message to append to the log")
@click.option(
    "-l",
    "--level",
    default="debug",
    type=click.Choice(["debug", "info", "notice", "warning", "error", "critical"], case_sensitive=False),
    help="the log level to use",
)
@click.option(
    "-n",
    "--name",
    default="CLI",
    type=str,
    help="logger name to display in the log record",
)
@click.option("--local-only", is_flag=True, help="don't send to MQTT; write only to local disk")
def log(message: str, level: str, name: str, local_only: bool) -> None:
    """
    Append a single log entry from the CLI.

    \b
    Examples:
      pio log -m "Calibration started" -l info
      pio log -m "Skipping pump test" --local-only
    """
    try:
        from pioreactor.logging import create_logger

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
    from pioreactor.http_response import summarize_error_response
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.pubsub import post_into_leader

    response = post_into_leader(f"/api/workers/{whoami.get_unit_name()}/blink")
    try:
        response.raise_for_status()
    except HTTPErrorStatus as error:
        raise click.ClickException(
            f"Unable to blink this Pioreactor. {summarize_error_response(response)}"
        ) from error


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
    from pioreactor.utils.job_manager import JobManager

    if not (job_name or experiment or job_source or all_jobs or job_id):
        raise click.Abort("Provide an option to kill. See --help")

    with JobManager() as jm:
        count = jm.kill_jobs(
            all_jobs=all_jobs, job_name=job_name, experiment=experiment, job_source=job_source, job_id=job_id
        )
    click.echo(f"Killed {count} job{'s' if count != 1 else ''}.")


@pio.group(name="jobs", short_help="job-related commands")
def jobs() -> None:
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
    pid: int,
) -> str:
    job_source_display = job_source or "unknown"
    ended_at_display = _format_timestamp_to_seconds(ended_at) or "still running"
    job_id_label = click.style(f"[job_id={job_id}]", fg="cyan")
    job_name_label = click.style(job_name, fg="green", bold=True)
    ended_at_label = (
        click.style(ended_at_display, fg="yellow", bold=True) if ended_at is None else ended_at_display
    )

    return (
        f"{job_id_label} {job_name_label} "
        f"experiment={experiment}, source={job_source_display}, pid={pid},"
        f"started_at={_format_timestamp_to_seconds(started_at)}, ended_at={ended_at_label}"
    )


def _show_job_history(running_only: bool = False) -> None:
    from pioreactor.utils.job_manager import JobManager

    with JobManager() as jm:
        jobs = jm.list_job_history(running_only=running_only)

    if not jobs:
        click.echo("No jobs recorded.")
        return

    for job in jobs:
        click.echo(_format_job_history_line(*job))


@jobs.group(name="list", short_help="list jobs current and previous", invoke_without_command=True)
@click.pass_context
def job_list(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is None:
        _show_job_history()


@job_list.command(name="running", short_help="show status of running job(s)")
def job_list_running() -> None:
    _show_job_history(running_only=True)


def _format_timestamp_to_seconds(timestamp: str | None) -> str:

    if timestamp is None:
        return ""

    try:
        from pioreactor.utils.timing import to_datetime

        dt = to_datetime(timestamp)
    except ValueError:
        return timestamp

    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


@jobs.command(name="info", short_help="show details for a job")
@click.option("--job-id", type=click.INT)
@click.option("--job-name", type=click.STRING)
def job_info(job_id: int | None, job_name: str | None) -> None:

    if job_id is None and job_name is None:
        click.echo("Provide --job-id or --job-name.")
        return

    if job_id is None and job_name is not None:
        from pioreactor.utils import get_running_pio_job_id

        job_id = get_running_pio_job_id(job_name)
        if job_id is None:
            click.echo(f"No running job found with name {job_name}.")
            return

    assert job_id is not None

    from pioreactor.utils.job_manager import JobManager

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
        _format_job_history_line(
            found_job_id, job_name, experiment, job_source, unit, started_at, ended_at, pid
        )
    )

    status_label = (
        click.style("running", fg="green", bold=True) if is_running else click.style("stopped", fg="red")
    )
    click.echo(f"status={status_label}")

    if not settings:
        return

    click.echo("published settings:")
    for setting, value, created_at, updated_at in settings:
        setting_label = click.style(setting, fg="cyan")
        created_at_display = _format_timestamp_to_seconds(created_at)
        updated_at_display = _format_timestamp_to_seconds(updated_at)

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


@jobs.command(name="set", short_help="set a running job setting")
@click.argument("job", type=click.STRING)
@click.argument("setting", type=click.STRING)
@click.argument("value", type=click.STRING)
def job_set(job: str, setting: str, value: str) -> None:
    """
    Set a published setting on a running job.

    \b
    Examples:
      pio jobs set stirring target_rpm 500
      pio jobs set stirring target-rpm 500
    """
    from pioreactor.pubsub import publish
    from pioreactor.pubsub import QOS

    unit = whoami.get_unit_name()
    exp = whoami.get_assigned_experiment_name(unit)
    setting = setting.replace("-", "_")

    # Job setting updates are command messages, not telemetry. Keep delivery above MQTT's QoS 0 default.
    publish(f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value, qos=QOS.AT_LEAST_ONCE)


@jobs.command(name="purge", short_help="remove a job record")
@click.option("--job-id", type=click.INT)
@click.option("--job-name", type=click.STRING)
def job_purge(job_id: int | None, job_name: str | None) -> None:
    if job_id is None and job_name is None:
        click.echo("Provide --job-id or --job-name.")
        return

    if job_id is None and job_name is not None:
        from pioreactor.utils import get_running_pio_job_id

        job_id = get_running_pio_job_id(job_name)
        if job_id is None:
            click.echo(f"No running job found with name {job_name}.")
            return

    assert job_id is not None

    from pioreactor.utils.job_manager import JobManager

    with JobManager() as jm:
        job = jm.get_job_info(job_id)

        if job is None:
            click.echo(f"No job found with job_id={job_id}.")
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
            model = "Unknown"
        except exc.NoWorkerFoundError:
            model = "N/A"

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


@pio.command(name="status", short_help="show local system status")
@click.option("--json", "json_output", is_flag=True, help="output as json")
def status(json_output: bool) -> None:
    """
    Show a quick, local-only status report for this unit.
    """
    from msgspec import to_builtins
    from pioreactor.cli.status_checks import collect_status_checks
    from pioreactor.cli.status_checks import worst_status

    checks = collect_status_checks()

    if json_output:
        click.echo(json.dumps({"status": worst_status(checks), "checks": to_builtins(checks)}))
        return

    status_colors = {"OK": "green", "WARN": "yellow", "FAIL": "red"}
    name_width = max(22, *(len(check.name) for check in checks))
    click.echo(f"{'Check':{name_width}s} {'Status':7s} Details")
    for check in checks:
        status_display = click.style(f"{check.status:7s}", fg=status_colors[check.status], bold=True)
        click.echo(f"{check.name:{name_width}s} {status_display} {check.details}")


@pio.command(name="repair", short_help="repair Pioreactor ownership and group permissions")
def repair() -> None:
    """
    Repair ownership and group permissions for the local .pioreactor tree and /run/pioreactor runtime tree.
    Clear stale Pioreactor runtime export artifacts.
    """
    dot_pioreactor_root = get_dot_pioreactor_root()
    if not dot_pioreactor_root.exists():
        raise click.ClickException(f"{dot_pioreactor_root} does not exist.")

    tools = require_repair_command_paths("sudo", "find", "chown", "chmod", "install", "touch", "systemctl")
    dot_pioreactor_commands = build_dot_pioreactor_repair_commands(dot_pioreactor_root, tools)
    runtime_commands = build_runtime_repair_commands(tools)
    command_groups = [
        (dot_pioreactor_commands, f"Repaired ownership and group permissions for {dot_pioreactor_root}."),
        (runtime_commands[:2], "Repaired runtime directories under /run/pioreactor."),
        (runtime_commands[2:3], "Cleared stale runtime export artifacts from /run/pioreactor/exports."),
        (runtime_commands[3:], "Repaired runtime cache files under /run/pioreactor/cache."),
    ]

    for commands, message in command_groups:
        for command in commands:
            subprocess.run(command, check=True)
        click.echo(message)

    restarted_services = restart_inactive_pioreactor_web_services(tools)
    if restarted_services:
        click.echo(f"Restarted inactive pioreactor-web.target services: {', '.join(restarted_services)}.")
    else:
        click.echo("pioreactor-web.target services are active.")

    restarted_startup_run_services = restart_inactive_pioreactor_startup_run_services(tools)
    if restarted_startup_run_services:
        click.echo(
            f"Restarted inactive pioreactor startup services: {', '.join(restarted_startup_run_services)}."
        )
    else:
        click.echo("Pioreactor startup services are active.")

    click.echo("Repair complete.")


@pio.group(short_help="manage the local caches")
def cache() -> None:
    """Inspect or clear local caches."""
    pass


@cache.command(name="list", short_help="list local cache names")
def list_caches() -> None:
    """Print sorted, unique cache names from persistent and intermittent storage."""
    config = get_config()
    cache_names: set[str] = set()
    for storage in ("temporary_cache", "persistent_cache"):
        db_path = Path(config.get("storage", storage))
        if not db_path.exists():
            continue

        with closing(sqlite3.connect(f"{db_path.absolute().as_uri()}?mode=ro", uri=True)) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name GLOB 'cache_*'"
            ).fetchall()
            cache_names.update(table_name.removeprefix("cache_") for (table_name,) in tables)

    for cache_name in sorted(cache_names):
        click.echo(cache_name)


def _cache_key_candidates(key: str, as_int: bool = False) -> list[Any]:
    if as_int:
        return [int(key)]

    candidates: list[Any] = [key]

    try:
        parsed_key = ast.literal_eval(key)
    except (ValueError, SyntaxError):
        parsed_key = None

    if parsed_key is not None and parsed_key != key:
        candidates.append(parsed_key)

    return candidates


@cache.command(name="view", short_help="print out the contents of a cache")
@click.argument("cache", metavar="CACHE")
@click.argument("key", metavar="KEY", required=False)
def view_cache(cache: str, key: str | None) -> None:
    """
    Print key/value pairs for a cache.

    \b
    Examples:
      pio cache view pwm
      pio cache view pwm 12
    """
    from pioreactor.utils import local_intermittent_storage
    from pioreactor.utils import local_persistent_storage

    # Cache names don't encode their storage type, so inspect both stores.
    # Opening an absent cache may create an empty table in that store.
    for cacher in [local_intermittent_storage, local_persistent_storage]:
        with cacher(cache) as c:
            if key is not None:
                for candidate in _cache_key_candidates(key):
                    if candidate in c:
                        click.echo(f"{click.style(candidate, bold=True)} = {c[candidate]}")
                        return

                continue

            for key_ in c.iterkeys():
                click.echo(f"{click.style(key_, bold=True)} = {c[key_]}")


@cache.command(name="purge", short_help="remove a key from a cache")
@click.argument("cache", metavar="CACHE")
@click.argument("key", metavar="KEY")
@click.option("--as-int", is_flag=True, help="evict after casting key to int, useful for gpio pins.")
def purge_cache(cache: str, key: str, as_int: bool) -> None:
    """
    Remove a single entry from a cache.

    \b
    Examples:
      pio cache purge pwm 12
      pio cache purge gpio 18 --as-int
      pio cache purge leader_multicast_get_cache "('multicast_get', 'calibrations', '/unit_api/calibrations', 'unit1')"
    """
    from pioreactor.utils import local_intermittent_storage
    from pioreactor.utils import local_persistent_storage

    removed = False
    removed_key: Any | None = None
    key_candidates = _cache_key_candidates(key, as_int=as_int)

    for cacher in [local_intermittent_storage, local_persistent_storage]:
        with cacher(cache) as c:
            for candidate in key_candidates:
                if candidate in c:
                    del c[candidate]
                    removed = True
                    removed_key = candidate
                    break

    if removed:
        click.echo(f"Removed key {removed_key} from cache '{cache}'.")
    else:
        click.echo(f"No entry for key {key_candidates[0]} found in cache '{cache}'.")


@pio.group()
def update() -> None:
    """
    Update Pioreactor software.
    """


@update.command(name="verify-release-archive", hidden=True)
@click.argument("archive_location")
@click.option("--expected-version")
def verify_release_archive_command(archive_location: str, expected_version: str | None) -> None:
    from pioreactor.release_archive import ReleaseArchiveVerificationError
    from pioreactor.release_archive import verify_release_archive

    try:
        verify_release_archive(archive_location, expected_version=expected_version)
    except ReleaseArchiveVerificationError as exc:
        raise click.ClickException(str(exc)) from exc


def get_non_prerelease_tags_of_pioreactor(repo: str) -> list[str]:
    """
    Returns a list of all the tag names associated with non-prerelease releases, sorted in descending order
    """
    from packaging.version import Version
    from pioreactor.mureq import get

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


def get_tag_to_install(repo: str, version_desired: str | None) -> str:
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
@click.option("-b", "--branch", callback=validate_git_ref_option, help="install from a branch on github")
@click.option("--sha", callback=validate_git_sha_option, help="install from a commit SHA on github")
@click.option(
    "--no-deps",
    is_flag=True,
    default=False,
    help="skip dependency resolution for branch/SHA updates",
)
@click.option(
    "-r",
    "--repo",
    help="install from a repo on github. Format: 'username/project'",
    default="pioreactor/pioreactor",
    callback=validate_github_repo_option,
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
    branch: str | None,
    sha: str | None,
    no_deps: bool,
    repo: str,
    source: str | None,
    version: str | None,
    defer_web_restart: bool = False,
) -> None:
    """
    Update the Pioreactor core software
    """
    from msgspec.json import encode as dumps
    from pioreactor.logging import create_logger
    from pioreactor.utils.timing import current_utc_timestamp

    # initialize logger and build commands based on input parameters
    logger = create_logger("update_app", unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT)
    logger.debug(
        "Starting app update. branch=%s sha=%s repo=%s source=%s version=%s no_deps=%s defer_web_restart=%s",
        branch,
        sha,
        repo,
        source,
        version,
        no_deps,
        defer_web_restart,
    )
    commands_and_priority, version_installed = get_update_app_commands(
        branch,
        repo,
        source,
        version,
        sha=sha,
        no_deps=no_deps,
        defer_web_restart=defer_web_restart,
    )
    logger.debug(
        "Prepared %s update commands. target_version=%s", len(commands_and_priority), version_installed
    )

    for index, (command, priority, allow_failure) in enumerate(
        sorted(commands_and_priority, key=lambda t: t[1]), start=1
    ):
        if whoami.is_testing_env():
            logger.debug("DRY-RUN (step %s, priority %s): %s", index, priority, join(command))
            continue

        logger.debug(
            "Running update step %s/%s: %s",
            index,
            len(commands_and_priority),
            join(command),
        )

        p = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if p.returncode != 0 and allow_failure:
            logger.debug("Update step %s returned %s but is allowed to fail.", index, p.returncode)
        elif p.returncode != 0:
            if p.stdout:
                logger.debug("Update step %s stdout: %s", index, p.stdout)
            if p.stderr:
                logger.debug("Update step %s stderr: %s", index, p.stderr)
            logger.error("Update failed at step %s with returncode %s. See System Logs", index, p.returncode)
            # end early
            raise click.Abort()
        elif p.stdout:
            logger.debug("Update step %s stdout: %s", index, p.stdout)
        if p.stderr:
            logger.debug("Update step %s stderr: %s", index, p.stderr)

    logger.notice(f"Updated Pioreactor app to version {version_installed}.")
    # everything work? Let's publish to MQTT. This is a terrible hack, as monitor should do this.
    from pioreactor.pubsub import publish

    publish(
        f"pioreactor/{whoami.get_unit_name()}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/versions/set",
        dumps({"app": version_installed, "timestamp": current_utc_timestamp()}),
    )


@update.command(name="firmware")
@click.option("-v", "--version", help="install a specific version, default is latest")
def update_firmware(version: str | None) -> None:
    """
    Update the RP2040 firmware.

    Firmware updates currently download only from pioreactor/pico-build GitHub releases;
    offline and custom sources are not supported.
    """

    from msgspec.json import decode as loads
    from pioreactor.logging import create_logger
    from pioreactor.mureq import get

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
                    (f"sudo wget -nv -O /usr/local/bin/main.elf {url}", 0),
                    ("sudo bash /usr/local/bin/load_rp2040.sh", 1),
                ]
            )

    for command, _ in sorted(commands_and_priority, key=lambda t: t[1]):
        logger.debug(command)
        p = subprocess.run(
            command,
            shell=True,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if p.returncode != 0:
            logger.debug(p.stderr)
            logger.error("Update failed.")
            # end early
            raise click.Abort()

    logger.info(f"Updated Pioreactor firmware to version {version_installed}.")


if whoami.am_I_leader():

    @pio.command(short_help="access the database's CLI")
    def db() -> None:
        """
        Open an interactive SQLite shell to the local Pioreactor database.

        \b
        Examples:
          pio db
        """
        import os
        from pioreactor.config import config

        os.system(f"sqlite3 {config.get('storage','database')} -column -header")

    @pio.command(short_help="tail MQTT")
    @click.option("--topic", "-t", default="pioreactor/#")
    def mqtt(topic: str) -> None:
        from pioreactor.config import config

        with subprocess.Popen(
            [
                "mosquitto_sub",
                "-v",
                "-t",
                topic,
                "-q",
                "2",
                "-F",
                "%19.19I||%t||%p",
                "-u",
                config.get("mqtt", "username", fallback="pioreactor"),
                "-P",
                config.get("mqtt", "password", fallback="raspberry"),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ) as process:
            assert process.stdout is not None
            for line in process.stdout:
                timestamp, topic, value = line.rstrip("\n").split("||")
                click.echo(
                    click.style(timestamp, fg="cyan")
                    + " | "
                    + click.style(topic, fg="bright_green")
                    + " | "
                    + click.style(value, fg="bright_yellow")
                )
