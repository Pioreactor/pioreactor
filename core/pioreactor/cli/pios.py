# -*- coding: utf-8 -*-
"""
CLI for running the commands on workers, or otherwise interacting with the workers.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

import click
from msgspec import DecodeError
from msgspec.json import encode as dumps
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
from pioreactor.pubsub import post_into
from pioreactor.utils import ClusterJobManager
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


@click.group(invoke_without_command=True)
@click.pass_context
def pios(ctx) -> None:
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

    def resolve_target_units(
        units_opt: tuple[str, ...] | None,
        experiments_opt: tuple[str, ...] | None,
        *,
        active_only: bool = True,
        include_leader: bool | None = False,
        filter_non_workers: bool = True,
        precedence: str = "intersection",  # "intersection" | "experiments" | "units"
    ) -> tuple[str, ...]:
        """Resolve the final list of target units for a `pios` command.

        Parameters
        - units_opt: The value from `--units` (may be empty). When empty/None, it implies
          a broadcast to all workers (active or all, see `active_only`).
        - experiments_opt: The value from `--experiments` (may be empty). When present,
          the set of target units is combined according to `precedence`.
        - active_only: If True, only consider active workers from inventory; if False,
          consider all workers in inventory.
        - include_leader:
          - True: always include the leader in the targets (even if not a worker).
          - False: always exclude the leader from the targets.
          - None: follow inventory (include the leader only if it is a worker).
        - filter_non_workers: If True, filter out any unit names not present in the
          selected inventory (active/all). If False, keep provided unit names even if
          not present in inventory.
        - precedence: How to combine `--units` and `--experiments` when both are
          provided. Options:
          - "intersection": final = units ∩ experiment_units (default, safest)
          - "experiments": final = experiment_units (units ignored)
          - "units": final = units (experiments ignored)

        Returns
        - A sorted tuple of unit names selected by the above logic.

        Notes
        - This function encapsulates all targeting rules to avoid Click callback
          ordering pitfalls. Command functions should pass raw options and rely on this
          resolver for consistent behavior.
        """

        experiments_opt = experiments_opt or tuple()

        # 1) Expand experiments to active workers
        exp_units: set[str] = set()
        for exp in experiments_opt:
            try:
                exp_units.update(get_active_workers_in_experiment(exp))
            except Exception:
                click.echo(f"Unable to get workers for experiment '{exp}'.", err=True)
        if experiments_opt and not exp_units:
            # Mirror previous UX when experiments yield no workers
            raise click.BadParameter(
                f"No active workers found for experiment(s): {', '.join(experiments_opt)}"
            )

        # 2) Resolve inventory base
        try:
            if active_only:
                inventory = set(get_active_workers_in_inventory())
            else:
                inventory = set(get_workers_in_inventory())
        except (HTTPException, DecodeError):
            click.echo("Unable to get workers from the inventory. Is the webserver down?", err=True)
            inventory = set()

        # 3) Expand units option
        if not units_opt:
            # Broadcast: start with all from inventory
            units_set = set(inventory)
        else:
            if filter_non_workers:
                units_set = {u for u in set(units_opt) if u in inventory}
            else:
                units_set = set(units_opt)

        # 4) Combine with experiments based on precedence
        if experiments_opt:
            if precedence == "intersection":
                units_set &= exp_units
            elif precedence == "experiments":
                units_set = set(exp_units)
            elif precedence == "units":
                pass

        # 5) Include/exclude leader
        leader = get_leader_hostname()
        if include_leader is True:
            units_set.add(leader)
        elif include_leader is False:
            units_set.discard(leader)

        if not units_set:
            raise click.BadParameter("No target workers matched the selection. Check --units/--experiments.")
        return tuple(sorted(units_set))

    def which_units(f):
        """Add common targeting options to a `pios` command.

        This only defines the options; it does not resolve them. Command handlers must
        call `resolve_target_units(...)` with appropriate arguments to compute the final
        targets. This avoids subtle interactions between Click callbacks and defaults.

        Semantics
        - If `--units` is omitted, behavior is equivalent to broadcasting to all workers
          (active-only by default in most commands).
        - If `--experiments` is provided, it restricts the target set according to the
          precedence chosen in `resolve_target_units` (defaults to intersection).
        - Leader inclusion is decided per-command via the `include_leader` argument to
          `resolve_target_units`.
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

    confirmation = click.option("-y", is_flag=True, help="Skip asking for confirmation.")
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

    def universal_identifier_to_all_active_workers(workers: tuple[str, ...]) -> tuple[str, ...]:
        try:
            active_workers = get_active_workers_in_inventory()
            # sometimes the webserver is down, and we don't want to crash due to that.
        except (HTTPException, DecodeError):
            click.echo("Unable to get workers from the inventory. Is the webserver down?", err=True)
            active_workers = tuple()

        if workers == (UNIVERSAL_IDENTIFIER,):
            return active_workers
        else:
            return tuple(u for u in set(workers) if u in active_workers)

    def universal_identifier_to_all_workers(
        workers: tuple[str, ...], filter_out_non_workers=True
    ) -> tuple[str, ...]:
        try:
            all_workers = get_workers_in_inventory()
            # sometimes the webserver is down, and we don't want to crash due to that.
        except (HTTPException, DecodeError):
            click.echo("Unable to get workers from the inventory. Is the webserver down?", err=True)
            all_workers = tuple()

        if filter_out_non_workers:
            include = lambda u: u in all_workers  # noqa: E731
        else:
            include = lambda u: True  # noqa: E731

        if workers == (UNIVERSAL_IDENTIFIER,):
            return all_workers
        else:
            return tuple(u for u in set(workers) if include(u))

    def add_leader(units: tuple[str, ...]) -> tuple[str, ...]:
        leader = get_leader_hostname()
        if leader not in units:
            units = units + (leader,)
        return units

    def remove_leader(units: tuple[str, ...]) -> tuple[str, ...]:
        leader = get_leader_hostname()
        return tuple(unit for unit in units if unit != leader)

    def save_config_files_to_db(units: tuple[str, ...], shared: bool, specific: bool) -> None:
        import sqlite3

        conn = sqlite3.connect(config["storage"]["database"])
        cur = conn.cursor()

        timestamp = current_utc_timestamp()
        sql = "INSERT INTO config_files_histories(timestamp,filename,data) VALUES(?,?,?)"

        if specific:
            for unit in units:
                try:
                    with open(f"/home/pioreactor/.pioreactor/config_{unit}.ini") as f:
                        cur.execute(sql, (timestamp, f"config_{unit}.ini", f.read()))
                except FileNotFoundError:
                    pass

        if shared:
            with open("/home/pioreactor/.pioreactor/config.ini") as f:
                cur.execute(sql, (timestamp, "config.ini", f.read()))

        conn.commit()
        conn.close()

    def sync_config_files(unit: str, shared: bool, specific: bool) -> None:
        """
        Moves

        1. the config.ini (if shared is True)
        2. config_{unit}.ini to the remote Pioreactor (if specific is True)

        Note: this function occurs in a thread
        """

        # move the global config.ini
        # there was a bug where if the leader == unit, the config.ini would get wiped
        if shared and unit != get_leader_hostname():
            localpath = "/home/pioreactor/.pioreactor/config.ini"
            remotepath = "/home/pioreactor/.pioreactor/config.ini"
            cp_file_across_cluster(unit, localpath, remotepath, timeout=30)

        # move the specific unit config.ini
        if specific:
            try:
                localpath = f"/home/pioreactor/.pioreactor/config_{unit}.ini"
                remotepath = "/home/pioreactor/.pioreactor/unit_config.ini"
                cp_file_across_cluster(unit, localpath, remotepath, timeout=30)

            except Exception as e:
                click.echo(
                    f"Error syncing config_{unit}.ini to {unit} - do they exist?",
                    err=True,
                )
                raise e
        return

    @pios.command("cp", short_help="cp a file across the cluster")
    @click.argument("filepath", type=click.Path(exists=True, resolve_path=True))
    @which_units
    @confirmation
    def cp(
        filepath: str,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        y: bool,
    ) -> None:
        units = resolve_target_units(
            units, experiments, active_only=False, include_leader=False, filter_non_workers=True
        )

        if not y:
            confirm = input(f"Confirm copying {filepath} onto {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

        logger = create_logger("cp", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)

        def _thread_function(unit: str) -> bool:
            logger.debug(f"Copying {filepath} to {unit}:{filepath}...")
            try:
                cp_file_across_cluster(unit, filepath, filepath, timeout=30)
                return True
            except Exception as e:
                logger.error(f"Error occurred copying to {unit}. See logs for more.")
                logger.debug(f"Error occurred: {e}.", exc_info=True)
                return False

        with ThreadPoolExecutor(max_workers=min(len(units), 6)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            sys.exit(1)

    @pios.command("rm", short_help="rm a file across the cluster")
    @click.argument("filepath", type=click.Path(resolve_path=True))
    @which_units
    @confirmation
    def rm(
        filepath: str,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        y: bool,
    ) -> None:
        units = resolve_target_units(
            units, experiments, active_only=False, include_leader=False, filter_non_workers=True
        )

        if not y:
            confirm = input(f"Confirm deleting {filepath} on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

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
            sys.exit(1)

    @pios.group(invoke_without_command=True)
    @click.option("-s", "--source", help="use a release-***.zip already on the workers")
    @click.option("-b", "--branch", help="specify a branch in repos")
    @which_units
    @confirmation
    @json_output
    @click.pass_context
    def update(
        ctx,
        source: str | None,
        branch: str | None,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        y: bool,
        json: bool,
    ) -> None:
        if ctx.invoked_subcommand is None:
            units = resolve_target_units(
                units, experiments, active_only=False, include_leader=True, filter_non_workers=True
            )

            if not y:
                confirm = input(f"Confirm updating app and ui on {units}? Y/n: ").strip()
                if confirm != "Y":
                    sys.exit(1)

            logger = create_logger("update", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
            options: dict[str, str | None] = {}
            args = ""

            if branch is not None:
                options["branch"] = branch
                args = f"--branch {branch}"
            elif source is not None:
                options["source"] = source
                args = f"--source {source}"

            def _thread_function(unit: str) -> tuple[bool, dict]:
                try:
                    r = post_into(
                        resolve_to_address(unit), "/unit_api/system/update", json={"options": options}
                    )
                    r.raise_for_status()
                    return True, r.json()
                except HTTPException as e:
                    logger.error(
                        f"Unable to update on {unit} due to server error: {e}. Attempting SSH method..."
                    )
                    try:
                        ssh(resolve_to_address(unit), f"pio update {args}")
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
                click.Abort()

    @update.command(name="app", short_help="update Pioreactor app on workers")
    @click.option("-b", "--branch", help="update to the github branch")
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
        repo: str | None,
        version: str | None,
        source: str | None,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        y: bool,
        json: bool,
    ) -> None:
        """
        Pulls and installs a Pioreactor software version across the cluster
        """

        units = resolve_target_units(
            units, experiments, active_only=False, include_leader=True, filter_non_workers=True
        )

        if not y:
            confirm = input(f"Confirm updating app on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

        logger = create_logger("update", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        options: dict[str, str | None] = {}
        args = ""

        # only one of these three is possible, mutually exclusive
        if version is not None:
            options["version"] = version
            args = f"--version {version}"
        elif branch is not None:
            options["branch"] = branch
            args = f"--branch {branch}"
        elif source is not None:
            options["source"] = source
            args = f"--source {source}"

        if repo is not None:
            options["repo"] = repo

        def _thread_function(unit: str) -> tuple[bool, dict]:
            try:
                r = post_into(
                    resolve_to_address(unit), "/unit_api/system/update/app", json={"options": options}
                )
                r.raise_for_status()
                return True, r.json()
            except HTTPException as e:
                logger.error(f"Unable to update on {unit} due to server error: {e}. Attempting SSH method...")
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
            click.Abort()

    @update.command(name="ui", short_help="update Pioreactor ui on workers")
    @click.option("-b", "--branch", help="update to the github branch")
    @click.option(
        "-r",
        "--repo",
        help="install from a repo on github. Format: username/project",
    )
    @click.option("-v", "--version", help="install a specific version, default is latest")
    @click.option("-s", "--source", help="install from a source")
    @which_units
    @confirmation
    @json_output
    def update_ui(
        branch: str | None,
        repo: str | None,
        version: str | None,
        source: str | None,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        y: bool,
        json: bool,
    ) -> None:
        """
        Pulls and installs the Pioreactor UI software version across the cluster
        """

        units = resolve_target_units(
            units, experiments, active_only=False, include_leader=True, filter_non_workers=True
        )

        if not y:
            confirm = input(f"Confirm updating ui on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

        logger = create_logger("update", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        options: dict[str, str | None] = {}
        args = ""

        # only one of these three is possible, mutually exclusive
        if version is not None:
            options["version"] = version
            args = f"--version {version}"
        elif branch is not None:
            options["branch"] = branch
            args = f"--branch {branch}"
        elif source is not None:
            options["source"] = source
            args = f"--source {source}"

        if repo is not None:
            options["repo"] = repo

        def _thread_function(unit: str) -> tuple[bool, dict]:
            try:
                r = post_into(
                    resolve_to_address(unit), "/unit_api/system/update/ui", json={"options": options}
                )
                r.raise_for_status()
                return True, r.json()
            except HTTPException as e:
                logger.error(f"Unable to update on {unit} due to server error: {e}. Attempting SSH method...")
                try:
                    ssh(resolve_to_address(unit), f"pio update ui {args}")
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
            click.Abort()

    @pios.group()
    def plugins():
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
        y: bool,
        json: bool,
    ) -> None:
        """
        Installs a plugin to worker and leader
        """

        units = resolve_target_units(
            units, experiments, active_only=False, include_leader=True, filter_non_workers=True
        )

        if not y:
            confirm = input(f"Confirm installing {plugin} on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

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
            click.Abort()

    @plugins.command("uninstall", short_help="uninstall a plugin on workers")
    @click.argument("plugin")
    @which_units
    @confirmation
    @json_output
    def uninstall_plugin(
        plugin: str, units: tuple[str, ...], experiments: tuple[str, ...], y: bool, json: bool
    ) -> None:
        """
        Uninstalls a plugin from worker and leader
        """

        units = resolve_target_units(
            units, experiments, active_only=False, include_leader=True, filter_non_workers=True
        )

        if not y:
            confirm = input(f"Confirm uninstalling {plugin} on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

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
            click.Abort()

    @pios.command(name="sync-configs", short_help="sync config")
    @click.option(
        "--shared",
        is_flag=True,
        help="sync the shared config.ini",
    )
    @click.option(
        "--specific",
        is_flag=True,
        help="sync the specific config.ini(s)",
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
        y: bool,
    ) -> None:
        """
        Deploys the shared config.ini and specific config.inis to the pioreactor units.

        If neither `--shared` not `--specific` are specified, both are set to true.
        """
        units = resolve_target_units(
            units,
            experiments,
            active_only=False,
            include_leader=True,  # maintain previous behaviour of always including leader
            filter_non_workers=False,  # allow specific units even if not in inventory
        )

        if not shared and not specific:
            shared = specific = True

        logger = create_logger("sync_configs", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)

        def _thread_function(unit: str) -> bool:
            logger.debug(f"Syncing configs on {unit}...")
            try:
                sync_config_files(unit, shared, specific)
                return True
            except RsyncError as e:
                logger.warning(f"Could not transfer config to {unit}. Is it online?")
                logger.debug(e, exc_info=True)
                return False
            except Exception as e:
                logger.warning(f"Encountered error syncing configs to {unit}: {e}")
                logger.debug(e, exc_info=True)
                return False

        if not skip_save:
            # save config.inis to database
            save_config_files_to_db(units, shared, specific)

        with ThreadPoolExecutor(max_workers=min(len(units), 6)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            sys.exit(1)

    @pios.command("kill", short_help="kill a job(s) on workers")
    @click.option("--job")
    @click.option("--all-jobs", is_flag=True, help="kill all worker jobs")
    @click.option("--experiment", type=click.STRING)
    @click.option("--job-source", type=click.STRING)
    @click.option("--job-name", type=click.STRING)
    @which_units
    @confirmation
    @json_output
    def kill(
        job: str | None,
        all_jobs: bool,
        experiment: str | None,
        job_source: str | None,
        job_name: str | None,
        units: tuple[str, ...],
        experiments: tuple[str, ...],
        y: bool,
        json: bool,
    ) -> None:
        """
        Send a SIG signal to JOB. JOB can be any Pioreactor job name, like "stirring".
        Example:

        > pios kill --job-name stirring


        Kill all worker jobs (i.e. this excludes leader jobs like monitor). Ignores `job` argument.

        > pios kill --all-jobs -y


        """
        units = resolve_target_units(
            units, experiments, active_only=True, include_leader=None, filter_non_workers=True
        )
        if not y:
            confirm = input(f"Confirm killing jobs on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

        with ClusterJobManager() as cm:
            results = cm.kill_jobs(
                units, all_jobs=all_jobs, experiment=experiment, job_source=job_source, job_name=job_name
            )

        if json:
            for success, api_result in results:
                api_result["status"] = "success" if success else "error"
                click.echo(dumps(api_result))

        if not all(success for (success, _) in results):
            click.Abort()

    @pios.command(
        name="run",
        context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
        short_help="run a job on workers",
    )
    @click.argument("job", type=click.STRING)
    @which_units
    @confirmation
    @json_output
    @click.pass_context
    def run(ctx, job: str, units: tuple[str, ...], experiments: tuple[str, ...], y: bool, json: bool) -> None:
        """
        Run a job on all, or specific, workers. Ex:

        > pios run stirring

        Will start stirring on all workers, after asking for confirmation.
        Each job has their own unique options:

        > pios run stirring --target-rpm 100
        > pios run od_reading

        To specify specific units, use the `--units` keyword multiple times, ex:

        > pios run stirring --units pio01 --units pio03

        """
        extra_args = list(ctx.args)

        if "unit" in extra_args:
            click.echo("Did you mean to use 'units' instead of 'unit'? Exiting.", err=True)
            sys.exit(1)

        units = resolve_target_units(
            units, experiments, active_only=True, include_leader=None, filter_non_workers=True
        )
        assert len(units) > 0, "Empty units!"

        if not y:
            confirm = input(f"Confirm running {job} on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

        data = parse_click_arguments(extra_args)

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
            click.Abort()

    @pios.command(
        name="shutdown",
        short_help="shutdown Pioreactors",
    )
    @which_units
    @confirmation
    def shutdown(units: tuple[str, ...], experiments: tuple[str, ...], y: bool) -> None:
        """Shutdown Pioreactor / Raspberry Pi.

        Leader handling: only shutdown the leader if it was explicitly included in
        `--units`. We therefore check the raw CLI parameter for the leader, and resolve
        targets with `include_leader=False` to avoid implicit leader inclusion.
        """
        also_shutdown_leader = get_leader_hostname() in units  # check raw CLI param
        units = resolve_target_units(
            units, experiments, active_only=False, include_leader=False, filter_non_workers=True
        )
        units_san_leader = units

        if not y:
            confirm = input(f"Confirm shutting down on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

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
    def reboot(units: tuple[str, ...], experiments: tuple[str, ...], y: bool) -> None:
        """Reboot Pioreactor / Raspberry Pi.

        Leader handling mirrors `shutdown`: only reboot the leader if explicitly
        requested via `--units`.
        """
        also_reboot_leader = get_leader_hostname() in units  # check raw CLI param
        units = resolve_target_units(
            units, experiments, active_only=False, include_leader=False, filter_non_workers=True
        )
        units_san_leader = units

        if not y:
            confirm = input(f"Confirm rebooting on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

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
    def update_settings(ctx, job: str, units: tuple[str, ...], experiments: tuple[str, ...], y: bool) -> None:
        """

        Examples:

        > pios update-settings stirring --target_rpm 500 --units worker1

        """
        from pioreactor.pubsub import create_client

        extra_args = {ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)}

        assert len(extra_args) > 0

        if not y:
            confirm = input(f"Confirm updating {job}'s {extra_args} on {units}? Y/n: ").strip()
            if confirm != "Y":
                sys.exit(1)

        units = resolve_target_units(
            units, experiments, active_only=True, include_leader=None, filter_non_workers=True
        )

        with create_client() as client:
            for unit in units:
                experiment = get_assigned_experiment_name(unit)
                for setting, value in extra_args.items():
                    setting = setting.replace("-", "_")
                    client.publish(f"pioreactor/{unit}/{experiment}/{job}/{setting}/set", value)


if __name__ == "__main__":
    pios()
