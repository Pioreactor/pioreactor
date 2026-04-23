# -*- coding: utf-8 -*-
"""
CLI for running the commands on workers, or otherwise interacting with the workers.
"""
import os
import re
import typing as t
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from shlex import quote
from typing import Any

import click
from msgspec import DecodeError
from msgspec.json import encode as dumps
from pioreactor import types as pt
from pioreactor.cluster_management import get_active_workers_in_experiment
from pioreactor.cluster_management import get_active_workers_in_inventory
from pioreactor.cluster_management import get_workers_in_inventory
from pioreactor.config import config
from pioreactor.config import get_leader_hostname
from pioreactor.exc import RoleError
from pioreactor.exc import RsyncError
from pioreactor.exc import SSHError
from pioreactor.logging import create_logger
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import get_from
from pioreactor.pubsub import post_into
from pioreactor.utils.job_manager import ClusterJobManager
from pioreactor.utils.networking import cp_file_across_cluster
from pioreactor.utils.networking import resolve_to_address
from pioreactor.utils.networking import ssh
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import am_I_leader
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env
from pioreactor.whoami import UNIVERSAL_EXPERIMENT
from pioreactor.whoami import UNIVERSAL_IDENTIFIER

GIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{4,40}$")


def validate_git_sha_option(_ctx: click.Context, _param: click.Parameter, value: str | None) -> str | None:
    if value is None:
        return None

    cleaned_value = value.strip()
    if not GIT_SHA_PATTERN.fullmatch(cleaned_value):
        raise click.BadParameter("Expected a commit SHA (4 to 40 hexadecimal characters).")

    return cleaned_value.lower()


@click.group(invoke_without_command=True)
@click.pass_context
def pios(ctx: click.Context) -> None:
    """
    Command each of the worker Pioreactors with the `pios` command.

    See full documentation here: https://docs.pioreactor.com/user-guide/cli#leader-only-commands-to-control-workers

    Report errors or feedback here: https://github.com/Pioreactor/pioreactor/issues
    """

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

    # this is run even if workers run `pios plugins etc.`
    if not am_I_leader():
        raise RoleError("workers cannot run `pios` commands. Try `pio` instead.")


if am_I_leader() or is_testing_env():

    UNIT_CONFIG_HISTORY_PREFIX = "unit_config.ini::"

    def _get_inventory_units(*, active_only: bool) -> set[pt.Unit]:
        try:
            return set(get_active_workers_in_inventory()) if active_only else set(get_workers_in_inventory())
        except (HTTPException, DecodeError):
            click.echo("Unable to get workers from the inventory. Is the webserver down?", err=True)
            return set()

    def _get_experiment_units(experiments_opt: tuple[str, ...] | None) -> set[pt.Unit]:
        if not experiments_opt:
            return set()

        exp_units: set[pt.Unit] = set()
        for exp in experiments_opt:
            try:
                exp_units.update(get_active_workers_in_experiment(exp))
            except Exception:
                click.echo(f"Unable to get workers for experiment '{exp}'.", err=True)

        if not exp_units:
            raise click.BadParameter(
                f"No active workers found for experiment(s): {', '.join(experiments_opt)}"
            )

        return exp_units

    def _get_explicit_units(units_opt: tuple[str, ...] | None) -> set[pt.Unit]:
        if not units_opt:
            return set()

        return {unit for unit in units_opt if unit != UNIVERSAL_IDENTIFIER}

    def _resolve_selector_units(
        units_opt: tuple[str, ...] | None,
        experiments_opt: tuple[str, ...] | None,
        *,
        active_only: bool = True,
    ) -> set[pt.Unit]:
        """Resolve units from the user's selector only.

        This step decides only between explicit units, experiment-derived units,
        and broadcast inventory. It does not apply leader policy or command-specific
        empty-target handling.
        """
        experiments_opt = experiments_opt or tuple()
        if units_opt and experiments_opt:
            raise click.BadParameter(
                "Use either --units or --experiments, not both. The combined selector is ambiguous."
            )

        explicit_units = _get_explicit_units(units_opt)

        inventory = _get_inventory_units(active_only=active_only)
        exp_units = _get_experiment_units(experiments_opt)

        unknown_units = explicit_units - inventory
        if unknown_units:
            raise click.BadParameter(
                f"Unknown unit(s): {', '.join(sorted(unknown_units))}. Check the inventory and retry."
            )

        if exp_units:
            return exp_units
        elif explicit_units:
            return explicit_units
        else:
            return set(inventory)

    def _apply_leader_policy(units: set[pt.Unit], include_leader: bool | None) -> set[pt.Unit]:
        leader = get_leader_hostname()
        if include_leader is True:
            return units | {leader}
        elif include_leader is False:
            return units - {leader}

        return units

    def resolve_active_job_units(
        units_opt: tuple[str, ...] | None,
        experiments_opt: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        selected_units = _resolve_selector_units(units_opt, experiments_opt, active_only=True)
        selected_units = _apply_leader_policy(selected_units, include_leader=None)
        if not selected_units:
            raise click.BadParameter("No target workers matched the selection. Check --units/--experiments.")
        return tuple(sorted(selected_units))

    def resolve_all_worker_units(
        units_opt: tuple[str, ...] | None,
        experiments_opt: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        selected_units = _resolve_selector_units(units_opt, experiments_opt, active_only=False)
        selected_units = _apply_leader_policy(selected_units, include_leader=False)
        return tuple(sorted(selected_units))

    def resolve_cluster_units_including_leader(
        units_opt: tuple[str, ...] | None,
        experiments_opt: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        selected_units = _resolve_selector_units(units_opt, experiments_opt, active_only=False)
        selected_units = _apply_leader_policy(selected_units, include_leader=True)
        if not selected_units:
            raise click.BadParameter("No target workers matched the selection. Check --units/--experiments.")
        return tuple(sorted(selected_units))

    def which_units(f: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        """Add common targeting options to a `pios` command.

        This only defines the options; it does not resolve them. Command handlers must
        call a resolver wrapper with appropriate command-specific policy.

        Semantics
        - If `--units` is omitted, behavior is equivalent to broadcasting to all workers
          (active-only by default in most commands).
        - If `--experiments` is provided, it targets active workers assigned to the
          selected experiment(s).
        - `--units` and `--experiments` cannot be combined.
        - Leader inclusion is decided per-command in the wrapper that consumes these options.
        """
        f = click.option(
            "--experiments",
            multiple=True,
            default=(),
            type=click.STRING,
            help="specify experiment(s) to select active workers from",
        )(f)

        f = click.option(
            "--units",
            multiple=True,
            default=(),
            type=click.STRING,
            help="specify worker unit(s); default is all",
        )(f)
        return f

    confirmation = click.option("--yes", "-y", is_flag=True, help="Skip asking for confirmation.")
    json_output = click.option("--json", is_flag=True, help="output as json")

    def parse_click_arguments(input_list: list[str]) -> dict:  # TODO: typed dict
        args: list[str] = []
        opts: dict[str, str | None] = {}

        i = 0
        while i < len(input_list):
            item = input_list[i]

            if item.startswith("--"):
                # Option detected
                option_name = item.lstrip("--")
                if i + 1 < len(input_list) and not input_list[i + 1].startswith("--"):
                    # Next item is the option's value
                    opts[option_name] = input_list[i + 1]
                    i += 1  # Skip the value
                else:
                    # No value provided for this option
                    opts[option_name] = None
            else:
                # Argument detected
                args.append(item)

            i += 1

        return {"args": args, "options": opts}

    def _format_timestamp_to_seconds(timestamp: str | None) -> str:
        if timestamp is None:
            return ""

        from pioreactor.utils.timing import to_datetime

        try:
            dt = to_datetime(timestamp)
        except ValueError:
            return timestamp

        return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")

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
        ended_at_display = _format_timestamp_to_seconds(ended_at) or "still running"
        job_id_label = click.style(f"[job_id={job_id}]", fg="cyan")
        job_name_label = click.style(job_name, fg="green", bold=True)
        ended_at_label = (
            click.style(ended_at_display, fg="yellow", bold=True) if ended_at is None else ended_at_display
        )

        return (
            f"{job_id_label} {job_name_label} "
            f"experiment={experiment}, source={job_source_display}, "
            f"started_at={_format_timestamp_to_seconds(started_at)}, ended_at={ended_at_label}"
        )

    def _show_cluster_job_history(
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        *,
        running_only: bool = False,
    ) -> None:
        units = resolve_active_job_units(units, experiments)
        if len(units) == 0:
            click.echo("No jobs recorded.")
            return

        endpoint = "/unit_api/jobs/running" if running_only else "/unit_api/jobs"
        all_rows: list[tuple[int, str, str, str | None, str, str, str | None]] = []

        def _thread_function(unit: str) -> tuple[bool, str, list[dict[str, Any]]]:
            try:
                response = get_from(resolve_to_address(unit), endpoint)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError("Expected list payload")
                return True, unit, payload
            except (HTTPException, ValueError) as e:
                click.echo(f"Unable to list jobs on {unit}: {e}", err=True)
                return False, unit, []

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        for _, unit, rows in results:
            for raw_row in rows:
                if not isinstance(raw_row, dict):
                    continue

                try:
                    job_id = int(raw_row["job_id"])
                    job_name = str(raw_row["job_name"])
                    experiment = str(raw_row["experiment"])
                    job_source_raw = raw_row.get("job_source")
                    row_unit = str(raw_row.get("unit", unit))
                    started_at = str(raw_row["started_at"])
                    ended_at_raw = raw_row.get("ended_at")
                except (KeyError, TypeError, ValueError):
                    continue

                all_rows.append(
                    (
                        job_id,
                        job_name,
                        experiment,
                        None if job_source_raw is None else str(job_source_raw),
                        row_unit,
                        started_at,
                        None if ended_at_raw is None else str(ended_at_raw),
                    )
                )

        if not all_rows:
            click.echo("No jobs recorded.")
            return

        rows_by_unit: dict[str, list[tuple[int, str, str, str | None, str, str, str | None]]] = defaultdict(
            list
        )
        for job_row in all_rows:
            rows_by_unit[job_row[4]].append(job_row)

        for unit in sorted(rows_by_unit):
            click.echo(click.style(unit, bold=True))
            unit_rows = sorted(rows_by_unit[unit], key=lambda row: row[5], reverse=True)
            for job_row in unit_rows:
                click.echo(f"  {_format_job_history_line(*job_row)}")

    def _unit_specific_history_key(unit: str) -> str:
        return f"{UNIT_CONFIG_HISTORY_PREFIX}{unit}"

    def save_config_files_to_db(shared: bool) -> None:
        import sqlite3

        conn = sqlite3.connect(config["storage"]["database"])
        cur = conn.cursor()

        timestamp = current_utc_timestamp()
        sql = "INSERT INTO config_files_histories(timestamp,filename,data) VALUES(?,?,?)"

        if shared:
            with (Path(os.environ["DOT_PIOREACTOR"]) / "config.ini").open(encoding="utf-8") as f:
                cur.execute(sql, (timestamp, "config.ini", f.read()))

        conn.commit()
        conn.close()

    def refresh_specific_config_snapshot(unit: str, persist: bool) -> None:
        import sqlite3

        if unit == get_leader_hostname():
            path = Path(os.environ["DOT_PIOREACTOR"]) / "unit_config.ini"
            if path.exists():
                contents = path.read_text(encoding="utf-8")
            else:
                contents = ""
        else:
            response = get_from(resolve_to_address(unit), "/unit_api/config/specific", timeout=15)
            response.raise_for_status()
            contents = response.content.decode("utf-8")

        if not persist:
            return

        conn = sqlite3.connect(config["storage"]["database"])
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO config_files_histories(timestamp,filename,data) VALUES(?,?,?)",
            (current_utc_timestamp(), _unit_specific_history_key(unit), contents),
        )
        conn.commit()
        conn.close()

    def sync_config_files(unit: str, shared: bool, specific: bool, persist: bool) -> None:
        """
        Executes the requested config sync operations for a single target unit.

        shared=True pushes the leader's config.ini onto workers.
        specific=True refreshes the leader-side snapshot of the unit's live unit_config.ini.
        """

        # move the global config.ini
        # there was a bug where if the leader == unit, the config.ini would get wiped
        if shared and unit != get_leader_hostname():
            localpath = str(Path(os.environ["DOT_PIOREACTOR"]) / "config.ini")
            remotepath = str(Path(os.environ["DOT_PIOREACTOR"]) / "config.ini")
            cp_file_across_cluster(unit, localpath, remotepath, timeout=15)

        if specific:
            refresh_specific_config_snapshot(unit, persist=persist)
        return

    @pios.command("cp", short_help="copy a local file from leader to workers")
    @click.argument("filepath", type=click.Path(exists=True, resolve_path=True))
    @which_units
    @confirmation
    def cp(
        filepath: str,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        yes: bool,
    ) -> None:
        """
        Copy a local file from the leader onto workers at the same path.

        \b
        Examples:
          pios cp /home/pioreactor/.pioreactor/config.ini --units worker1
          pios cp /home/pioreactor/.pioreactor/plugins/my_plugin.py
        """
        units = resolve_all_worker_units(units, experiments)

        if len(units) == 0:
            return

        if not yes:
            confirm = input(f"Confirm copying {filepath} onto {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        logger = create_logger("cp", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)

        def _thread_function(unit: str) -> bool:
            logger.debug(f"Copying {filepath} to {unit}:{filepath}...")
            try:
                cp_file_across_cluster(unit, filepath, filepath, timeout=15)
                return True
            except Exception as e:
                logger.error(f"Error occurred copying to {unit}. See logs for more.")
                logger.debug(f"Error occurred: {e}.", exc_info=True)
                return False

        with ThreadPoolExecutor(max_workers=min(len(units), 6)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()

    @pios.command("rm", short_help="remove a file on workers")
    @click.argument("filepath", type=click.Path(resolve_path=True))
    @which_units
    @confirmation
    def rm(
        filepath: str,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        yes: bool,
    ) -> None:
        """
        Remove a file from workers.

        \b
        Examples:
          pios rm /home/pioreactor/.pioreactor/plugins/my_plugin.py --units worker1
          pios rm /home/pioreactor/.pioreactor/unit_config.ini --experiments testing
        """
        units = resolve_all_worker_units(units, experiments)

        if len(units) == 0:
            return

        if not yes:
            confirm = input(f"Confirm deleting {filepath} on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        logger = create_logger("rm", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)

        def _thread_function(unit: str) -> bool:
            try:
                logger.debug(f"deleting {unit}:{filepath}...")
                r = post_into(
                    resolve_to_address(unit), "/unit_api/system/remove_file", json={"filepath": filepath}
                )
                r.raise_for_status()
                return True

            except HTTPException as e:
                logger.error(f"Unable to remove file on {unit} due to server error: {e}.")
                return False

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()

    @pios.group(invoke_without_command=True)
    @click.option("-s", "--source", help="use a release-***.zip already on the workers")
    @click.option("-b", "--branch", help="specify a branch in repos")
    @click.option("--sha", callback=validate_git_sha_option, help="specify a commit SHA in repos")
    @click.option(
        "-r",
        "--repo",
        help="install from a repo on github. Format: username/project",
    )
    @click.option("-v", "--version", help="install a specific version, default is latest")
    @click.option(
        "--no-deps",
        is_flag=True,
        default=False,
        help="skip dependency resolution for branch/SHA updates",
    )
    @which_units
    @confirmation
    @json_output
    @click.pass_context
    def update(
        ctx: click.Context,
        source: str | None,
        branch: str | None,
        sha: str | None,
        repo: str | None,
        version: str | None,
        no_deps: bool,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        yes: bool,
        json: bool,
    ) -> None:
        """
        Update Pioreactor software across workers.
        """
        if ctx.invoked_subcommand is None:
            ctx.invoke(
                update_app,
                branch=branch,
                sha=sha,
                no_deps=no_deps,
                repo=repo,
                version=version,
                source=source,
                units=units,
                experiments=experiments,
                yes=yes,
                json=json,
            )

    @update.command(name="app", short_help="update Pioreactor app on workers")
    @click.option("-b", "--branch", help="update to the github branch")
    @click.option("--sha", callback=validate_git_sha_option, help="update to a github commit SHA")
    @click.option(
        "--no-deps",
        is_flag=True,
        default=False,
        help="skip dependency resolution for branch/SHA updates",
    )
    @click.option(
        "-r",
        "--repo",
        help="install from a repo on github. Format: username/project",
    )
    @click.option("-v", "--version", help="install a specific version, default is latest")
    @click.option("-s", "--source", help="install from a source, whl or release archive")
    @which_units
    @confirmation
    @json_output
    def update_app(
        branch: str | None,
        sha: str | None,
        no_deps: bool,
        repo: str | None,
        version: str | None,
        source: str | None,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        yes: bool,
        json: bool,
    ) -> None:
        """
        Pulls and installs a Pioreactor software version.

        With no selector, this targets the leader and all workers. If `--units`
        or `--experiments` is provided, only the selected workers are updated.
        """

        if units or experiments:
            units = resolve_all_worker_units(units, experiments)
        else:
            units = resolve_cluster_units_including_leader(units, experiments)

        if len(units) == 0:
            return

        if not yes:
            confirm = input(f"Confirm updating app on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        logger = create_logger("update", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        options: dict[str, str | None] = {}
        args = ""

        # only one of these four is possible, mutually exclusive
        if version is not None:
            options["version"] = version
            args = f"--version {quote(version)}"
        elif branch is not None:
            options["branch"] = branch
            args = f"--branch {quote(branch)}"
        elif sha is not None:
            options["sha"] = sha
            args = f"--sha {quote(sha)}"
        elif source is not None:
            options["source"] = source
            args = f"--source {quote(source)}"

        if no_deps:
            options["no_deps"] = None
            args = f"{args} --no-deps".strip()

        if repo is not None:
            options["repo"] = repo
            args = f"{args} --repo {quote(repo)}".strip()

        def _thread_function(unit: str) -> tuple[bool, dict]:
            try:
                r = post_into(
                    resolve_to_address(unit), "/unit_api/system/update/app", json={"options": options}
                )
                r.raise_for_status()
                return True, r.json()
            except HTTPException as e:
                logger.warning(
                    f"Unable to update on {unit} due to server error: {e}. Attempting SSH method to execute `pio update app {args}`..."
                )
                try:
                    ssh(resolve_to_address(unit), f"pio update app {args}")
                    return True, {"unit": unit}
                except SSHError as e:
                    logger.error(f"Unable to update on {unit} due to SSH error: {e}.")
                return False, {"unit": unit}

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if json:
            for success, api_result in results:
                api_result["status"] = "success" if success else "error"
                click.echo(dumps(api_result))

        if not all(success for (success, _) in results):
            raise click.Abort()

    @pios.group()
    def plugins() -> None:
        """
        Manage plugins on workers.

        \b
        Examples:
          pios plugins install pioreactor-foo
          pios plugins install /path/to/plugin.whl --units worker1
          pios plugins uninstall pioreactor-foo
        """
        pass

    @plugins.command("install", short_help="install a plugin on workers")
    @click.argument("plugin")
    @click.option(
        "--source",
        type=str,
        help="Install from a url, ex: https://github.com/user/repository/archive/branch.zip, or wheel file",
    )
    @which_units
    @confirmation
    @json_output
    def install_plugin(
        plugin: str,
        source: str | None,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        yes: bool,
        json: bool,
    ) -> None:
        """
        Install a plugin on workers (and leader if targeted).

        \b
        Examples:
          pios plugins install pioreactor-foo
          pios plugins install /path/to/plugin.whl --units worker1
          pios plugins install pioreactor-foo --source https://example.com/release.zip
        """

        units = resolve_cluster_units_including_leader(units, experiments)

        if len(units) == 0:
            return

        if not yes:
            confirm = input(f"Confirm installing {plugin} on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        logger = create_logger("install_plugin", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        commands = {"args": [plugin], "options": {}}

        if source:
            commands["options"] = {"source": source}

        def _thread_function(unit: str) -> tuple[bool, dict]:
            try:
                r = post_into(
                    resolve_to_address(unit), "/unit_api/plugins/install", json=commands, timeout=60
                )
                r.raise_for_status()
                return True, r.json()
            except HTTPException as e:
                logger.error(f"Unable to install plugin on {unit} due to server error: {e}.")
                return False, {"unit": unit}

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if json:
            for success, api_result in results:
                api_result["status"] = "success" if success else "error"
                click.echo(dumps(api_result))

        if not all(success for (success, _) in results):
            raise click.Abort()

    @plugins.command("uninstall", short_help="uninstall a plugin on workers")
    @click.argument("plugin")
    @which_units
    @confirmation
    @json_output
    def uninstall_plugin(
        plugin: str, units: tuple[str, ...], experiments: tuple[str, ...], yes: bool, json: bool
    ) -> None:
        """
        Uninstall a plugin from workers (and leader if targeted).

        \b
        Examples:
          pios plugins uninstall pioreactor-foo
          pios plugins uninstall pioreactor-foo --units worker1
        """

        units = resolve_cluster_units_including_leader(units, experiments)

        if len(units) == 0:
            return

        if not yes:
            confirm = input(f"Confirm uninstalling {plugin} on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        logger = create_logger("uninstall_plugin", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        commands = {"args": [plugin]}

        def _thread_function(unit: str) -> tuple[bool, dict]:
            try:
                r = post_into(
                    resolve_to_address(unit), "/unit_api/plugins/uninstall", json=commands, timeout=60
                )
                r.raise_for_status()
                return True, r.json()

            except HTTPException as e:
                logger.error(f"Unable to uninstall plugin on {unit} due to server error: {e}.")
                return False, {"unit": unit}

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if json:
            for success, api_result in results:
                api_result["status"] = "success" if success else "error"
                click.echo(dumps(api_result))

        if not all(success for (success, _) in results):
            raise click.Abort()

    @pios.command(name="sync-configs", short_help="sync config")
    @click.option(
        "--shared",
        is_flag=True,
        help="sync the shared config.ini",
    )
    @click.option(
        "--specific",
        is_flag=True,
        help="refresh leader-side snapshots of unit-specific unit_config.ini files",
    )
    @click.option(
        "--skip-save",
        is_flag=True,
        help="don't save to db",
    )
    @which_units
    @confirmation
    def sync_configs(
        shared: bool,
        specific: bool,
        skip_save: bool,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        yes: bool,
    ) -> None:
        """
        Pushes shared config.ini and/or refreshes unit-specific config snapshots.

        If neither `--shared` not `--specific` are specified, both are set to true.

        \b
        Examples:
          pios sync-configs --shared
          pios sync-configs --specific --units worker1
        """
        units = resolve_cluster_units_including_leader(units, experiments)

        if len(units) == 0:
            return

        if not shared and not specific:
            shared = specific = True

        logger = create_logger("sync_configs", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)

        def _thread_function(unit: str) -> bool:
            logger.debug(f"Syncing configs on {unit}...")
            try:
                sync_config_files(unit, shared, specific, persist=not skip_save)
                return True
            except RsyncError as e:
                logger.warning(f"Could not transfer config to {unit}.")
                logger.debug(e, exc_info=True)
                return False
            except HTTPException as e:
                logger.warning(f"Could not refresh unit-specific config snapshot from {unit}: {e}")
                logger.debug(e, exc_info=True)
                return False
            except Exception as e:
                logger.warning(f"Encountered error syncing configs to {unit}: {e}")
                logger.debug(e, exc_info=True)
                return False

        if not skip_save and shared:
            save_config_files_to_db(shared=True)

        with ThreadPoolExecutor(max_workers=min(len(units), 6)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()

    @pios.group(name="jobs", short_help="job-related commands")
    def jobs() -> None:
        """Interact with worker jobs."""
        pass

    @jobs.group(name="list", short_help="list jobs current and previous", invoke_without_command=True)
    @which_units
    @click.pass_context
    def list_jobs(ctx: click.Context, units: tuple[str, ...], experiments: tuple[str, ...]) -> None:
        if ctx.invoked_subcommand is None:
            _show_cluster_job_history(units, experiments, running_only=False)

    @list_jobs.command(name="running", short_help="show status of running job(s)")
    @which_units
    def list_running_jobs(units: tuple[str, ...], experiments: tuple[str, ...]) -> None:
        _show_cluster_job_history(units, experiments, running_only=True)

    @pios.command("kill", short_help="kill a job(s) on workers")
    @click.option("--all-jobs", is_flag=True, help="kill all worker jobs")
    @click.option("--experiment", type=click.STRING)
    @click.option("--job-source", type=click.STRING)
    @click.option("--job-name", type=click.STRING)
    @which_units
    @confirmation
    @json_output
    def kill(
        all_jobs: bool,
        experiment: str | None,
        job_source: str | None,
        job_name: str | None,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        yes: bool,
        json: bool,
    ) -> None:
        """
        Kill jobs on workers by name, experiment, or source.

        \b
        Examples:
          pios kill --job-name stirring
          pios kill --experiment testing2
          pios kill --all-jobs -y
        """
        units = resolve_active_job_units(units, experiments)

        if len(units) == 0:
            return

        if not yes:
            confirm = input(f"Confirm killing jobs on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        with ClusterJobManager() as cm:
            results = cm.kill_jobs(
                units, all_jobs=all_jobs, experiment=experiment, job_source=job_source, job_name=job_name
            )

        if json:
            for success, api_result in results:
                api_result["status"] = "success" if success else "error"
                click.echo(dumps(api_result))

        if not all(success for (success, _) in results):
            raise click.Abort()

    @pios.command(
        name="run",
        context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
        short_help="run a job on workers",
    )
    @click.option(
        "--config-override",
        nargs=3,
        multiple=True,
        metavar="<section> <param> <value>",
        help="Temporarily override a config value while running the job",
    )
    @click.argument("job", type=click.STRING)
    @which_units
    @confirmation
    @json_output
    @click.pass_context
    def run(
        ctx: click.Context,
        job: str,
        config_override: tuple[tuple[str, str, str], ...],
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        yes: bool,
        json: bool,
    ) -> None:
        """
        Run a job on all, or specific, workers.

        Will start stirring on all workers, after asking for confirmation.
        Each job has their own unique options.

        \b
        Examples:
          pios run stirring
          pios run stirring --target-rpm 100
          pios run od_reading
          pios run stirring --units pio01 --units pio03

        """
        extra_args = list(ctx.args)

        if "unit" in extra_args:
            click.echo("Did you mean to use 'units' instead of 'unit'? Exiting.", err=True)
            raise click.Abort()

        units = resolve_active_job_units(units, experiments)

        if len(units) == 0:
            return

        if not yes:
            confirm = input(f"Confirm running {job} on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        data = parse_click_arguments(extra_args)
        data["config_overrides"] = [list(override) for override in config_override]

        def _thread_function(unit: str) -> tuple[bool, dict]:
            try:
                r = post_into(resolve_to_address(unit), f"/unit_api/jobs/run/job_name/{job}", json=data)
                r.raise_for_status()
                return True, r.json()
            except HTTPException as e:
                click.echo(f"Unable to execute run command on {unit} due to server error: {e}.")
                return False, {"unit": unit}

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if json:
            for success, api_result in results:
                api_result["status"] = "success" if success else "error"
                click.echo(dumps(api_result))

        if not all(success for (success, _) in results):
            raise click.Abort()

    @pios.command(
        name="shutdown",
        short_help="shutdown Pioreactors",
    )
    @which_units
    @confirmation
    def shutdown(units: tuple[str, ...], experiments: tuple[str, ...], yes: bool) -> None:
        """Shutdown Pioreactor / Raspberry Pi.

        Leader handling: only shutdown the leader if it was explicitly included in
        `--units`. We therefore check the raw CLI parameter for the leader, and resolve
        targets with `include_leader=False` to avoid implicit leader inclusion.
        """
        also_shutdown_leader = get_leader_hostname() in units  # check raw CLI param
        units = resolve_all_worker_units(units, experiments)
        units_san_leader = units

        if not yes:
            confirm = input(f"Confirm shutting down on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        def _thread_function(unit: str) -> bool:
            try:
                post_into(resolve_to_address(unit), "/unit_api/system/shutdown", timeout=60)
                return True
            except HTTPException as e:
                click.echo(f"Unable to install plugin on {unit} due to server error: {e}.")
                return False

        if len(units_san_leader) > 0:
            with ThreadPoolExecutor(max_workers=len(units_san_leader)) as executor:
                executor.map(_thread_function, units_san_leader)

        # we delay shutdown leader (if asked), since it would prevent
        # executing the shutdown cmd on other workers
        if also_shutdown_leader:
            post_into(resolve_to_address(get_leader_hostname()), "/unit_api/shutdown", timeout=60)

    @pios.command(name="reboot", short_help="reboot Pioreactors")
    @which_units
    @confirmation
    def reboot(units: tuple[str, ...], experiments: tuple[str, ...], yes: bool) -> None:
        """Reboot Pioreactor / Raspberry Pi.

        Leader handling mirrors `shutdown`: only reboot the leader if explicitly
        requested via `--units`.
        """
        also_reboot_leader = get_leader_hostname() in units  # check raw CLI param
        units = resolve_all_worker_units(units, experiments)
        units_san_leader = units

        if not yes:
            confirm = input(f"Confirm rebooting on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        def _thread_function(unit: str) -> bool:
            try:
                post_into(resolve_to_address(unit), "/unit_api/system/reboot", timeout=60)
                return True
            except HTTPException as e:
                click.echo(f"Unable to install plugin on {unit} due to server error: {e}.")
                return False

        if len(units_san_leader) > 0:
            with ThreadPoolExecutor(max_workers=len(units_san_leader)) as executor:
                executor.map(_thread_function, units_san_leader)

        # we delay rebooting leader (if asked), since it would prevent
        # executing the reboot cmd on other workers
        if also_reboot_leader:
            post_into(resolve_to_address(get_leader_hostname()), "/unit_api/reboot", timeout=60)

    @pios.command(
        name="update-settings",
        context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
        short_help="update settings on a job on workers",
    )
    @click.argument("job", type=click.STRING)
    @which_units
    @confirmation
    @click.pass_context
    def update_settings(
        ctx: click.Context, job: str, units: tuple[str, ...], experiments: tuple[str, ...], yes: bool
    ) -> None:
        """
        Update settings on a running job across workers.

        \b
        Examples:
          pios update-settings stirring --target_rpm 500 --units worker1
          pios update-settings od_reading --interval 10 --experiments testing2
        """
        from pioreactor.pubsub import create_client
        from pioreactor.pubsub import QOS

        extra_args = {ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)}

        assert len(extra_args) > 0

        if not yes:
            confirm = input(f"Confirm updating {job}'s {extra_args} on {units}? Y/n: ").strip().upper()
            if confirm != "Y":
                raise click.Abort()

        units = resolve_active_job_units(units, experiments)

        with create_client() as client:
            for unit in units:
                experiment = get_assigned_experiment_name(unit)
                for setting, value in extra_args.items():
                    setting = setting.replace("-", "_")
                    # This CLI path is short-lived, so wait before teardown after sending a settings command.
                    msg = client.publish(
                        f"pioreactor/{unit}/{experiment}/{job}/{setting}/set",
                        value,
                        qos=QOS.AT_LEAST_ONCE,
                    )
                    msg.wait_for_publish(timeout=2.0)


if __name__ == "__main__":
    pios()
