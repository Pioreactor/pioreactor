# -*- coding: utf-8 -*-
"""
CLI for running the commands on workers
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import click

from pioreactor.config import config
from pioreactor.config import get_active_workers_in_inventory
from pioreactor.config import get_leader_hostname
from pioreactor.config import get_workers_in_inventory
from pioreactor.logging import create_logger
from pioreactor.utils.networking import add_local
from pioreactor.utils.networking import cp_file_across_cluster
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import am_I_leader
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env
from pioreactor.whoami import UNIVERSAL_EXPERIMENT
from pioreactor.whoami import UNIVERSAL_IDENTIFIER


@click.group()
def pios() -> None:
    """
    Command each of the worker Pioreactors with the `pios` command.

    See full documentation here: https://docs.pioreactor.com/user_guide/Advanced/Command%20line%20interface#leader-only-commands-to-control-workers

    Report errors or feedback here: https://github.com/Pioreactor/pioreactor/issues
    """
    if not am_I_leader() and not is_testing_env():
        click.echo("workers cannot run `pios` commands. Try `pio` instead.", err=True)
        raise click.Abort()

    if len(get_active_workers_in_inventory()) == 0:
        logger = create_logger("CLI", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        logger.warning("No active workers. See `cluster.inventory` section in config.ini.")


if am_I_leader():

    def universal_identifier_to_all_active_workers(units: tuple[str, ...]) -> tuple[str, ...]:
        if units == (UNIVERSAL_IDENTIFIER,):
            units = get_active_workers_in_inventory()
        return units

    def universal_identifier_to_all_workers(units: tuple[str, ...]) -> tuple[str, ...]:
        if units == (UNIVERSAL_IDENTIFIER,):
            units = get_workers_in_inventory()
        return units

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
            cp_file_across_cluster(unit, localpath, remotepath)

        # move the specific unit config.ini
        if specific:
            try:
                localpath = f"/home/pioreactor/.pioreactor/config_{unit}.ini"
                remotepath = "/home/pioreactor/.pioreactor/unit_config.ini"
                cp_file_across_cluster(unit, localpath, remotepath)

            except Exception as e:
                click.echo(
                    f"Did you forget to create a config_{unit}.ini to deploy to {unit}?",
                    err=True,
                )
                raise e
        return

    @pios.command("cp", short_help="cp a file across the cluster")
    @click.argument("filepath", type=click.Path(exists=True, resolve_path=True))
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a Pioreactor name, default is all active non-leader units",
    )
    def cp(
        filepath: str,
        units: tuple[str, ...],
    ) -> None:
        logger = create_logger("cp", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        units = remove_leader(universal_identifier_to_all_workers(units))

        def _thread_function(unit: str) -> bool:
            logger.debug(f"Moving {filepath} to {unit}:{filepath}...")
            try:
                cp_file_across_cluster(unit, filepath, filepath)
                return True
            except Exception as e:
                logger.error(f"Error occurred: {e}. See logs for more.")
                logger.debug(f"Error occurred: {e}.", exc_info=True)
                return False

        for unit in units:
            _thread_function(unit)

    @pios.command("rm", short_help="rm a file across the cluster")
    @click.argument("filepath", type=click.Path(exists=True, resolve_path=True))
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a Pioreactor name, default is all active non-leader units",
    )
    @click.option("-y", is_flag=True, help="Skip asking for confirmation.")
    def rm(
        filepath: str,
        units: tuple[str, ...],
        y: bool,
    ) -> None:
        logger = create_logger("rm", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        units = remove_leader(universal_identifier_to_all_workers(units))

        from sh import ssh  # type: ignore
        from sh import ErrorReturnCode_255  # type: ignore
        from sh import ErrorReturnCode_1
        from shlex import join  # https://docs.python.org/3/library/shlex.html#shlex.quote

        command = join(["rm", filepath])

        if not y:
            confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
            if confirm != "Y":
                raise click.Abort()

        def _thread_function(unit: str) -> bool:
            logger.debug(f"Removing {unit}:{filepath}...")
            try:
                ssh(add_local(unit), command)
                return True
            except ErrorReturnCode_255 as e:
                logger.error(f"Unable to connect to unit {unit}. {e.stderr.decode()}")
                logger.debug(e, exc_info=True)
                return False
            except ErrorReturnCode_1 as e:
                logger.error(f"Error occurred: {e}. See logs for more.")
                return False

        for unit in units:
            _thread_function(unit)

    @pios.command("update", short_help="update PioreactorApp on workers")
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a Pioreactor name, default is all active units",
    )
    @click.option("-b", "--branch", help="update to the github branch")
    @click.option(
        "-r",
        "--repo",
        help="install from a repo on github. Format: username/project",
    )
    @click.option("-v", "--version", help="install a specific version, default is latest")
    @click.option("-y", is_flag=True, help="Skip asking for confirmation.")
    def update(
        units: tuple[str, ...],
        branch: Optional[str],
        repo: Optional[str],
        version: Optional[str],
        y: bool,
    ) -> None:
        """
        Pulls and installs a Pioreactor software version across the cluster
        """
        from sh import ssh  # type: ignore
        from sh import ErrorReturnCode_255  # type: ignore
        from sh import ErrorReturnCode_1
        from shlex import join

        # type: ignore

        logger = create_logger("update", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
        if version is not None:
            commands = ["pio", "update", "app", "-v", version]
        elif branch is not None:
            commands = ["pio", "update", "app", "-b", branch]
        else:
            commands = ["pio", "update", "app"]

        if repo is not None:
            commands.extend(["-r", repo])

        command = join(commands)

        units = universal_identifier_to_all_workers(units)

        if not y:
            confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
            if confirm != "Y":
                raise click.Abort()

        def _thread_function(unit: str):
            logger.debug(f"Executing `{command}` on {unit}...")
            try:
                ssh(add_local(unit), command)
                return True
            except ErrorReturnCode_255 as e:
                logger.error(f"Unable to connect to unit {unit}. {e.stderr.decode()}")
                logger.debug(e, exc_info=True)
                return False
            except ErrorReturnCode_1 as e:
                logger.error(f"Error occurred: {e}. See logs for more.")
                logger.debug(e.stderr, exc_info=True)
                return False

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()

    @pios.command("install-plugin", short_help="install a plugin on workers")
    @click.argument("plugin")
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a Pioreactor name, default is all active units",
    )
    def install_plugin(plugin: str, units: tuple[str, ...]) -> None:
        """
        Installs a plugin to worker and leader
        """
        from sh import ssh  # type: ignore
        from sh import ErrorReturnCode_255  # type: ignore
        from sh import ErrorReturnCode_1  # type: ignore

        logger = create_logger(
            "install_plugin", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT
        )

        command = f"pio install-plugin {plugin}"

        def _thread_function(unit: str):
            logger.debug(f"Executing `{command}` on {unit}...")
            try:
                ssh(add_local(unit), command)
                return True
            except ErrorReturnCode_255 as e:
                logger.error(f"Unable to connect to unit {unit}. {e.stderr.decode()}")
                logger.debug(e, exc_info=True)
                return False
            except ErrorReturnCode_1 as e:
                logger.error(f"Error occurred: {e}. See logs for more.")
                logger.debug(e.stderr, exc_info=True)
                return False

        units = add_leader(universal_identifier_to_all_workers(units))
        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()

    @pios.command("uninstall-plugin", short_help="uninstall a plugin on workers")
    @click.argument("plugin")
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a Pioreactor name, default is all active units",
    )
    def uninstall_plugin(plugin: str, units: tuple[str, ...]) -> None:
        """
        Uninstalls a plugin from worker and leader
        """

        from sh import ssh  # type: ignore
        from sh import ErrorReturnCode_255  # type: ignore
        from sh import ErrorReturnCode_1  # type: ignore

        logger = create_logger(
            "uninstall_plugin", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT
        )

        command = f"pio uninstall-plugin {plugin}"

        def _thread_function(unit: str):
            logger.debug(f"Executing `{command}` on {unit}...")
            try:
                ssh(add_local(unit), command)
                return True
            except ErrorReturnCode_255 as e:
                logger.error(f"Unable to connect to unit {unit}. {e.stderr.decode()}")
                logger.debug(e, exc_info=True)
                return False
            except ErrorReturnCode_1 as e:
                logger.error(f"Error occurred: {e}. See logs for more.")
                logger.debug(e.stderr, exc_info=True)
                return False

        units = add_leader(universal_identifier_to_all_workers(units))
        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()

    @pios.command(name="sync-configs", short_help="sync config")
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a hostname, default is all active units",
    )
    @click.option(
        "--shared",
        is_flag=True,
        help="sync the shared config.ini",
    )
    @click.option(
        "--specific",
        is_flag=True,
        help="sync the worker specific config.ini(s)",
    )
    @click.option(
        "--skip-save",
        is_flag=True,
        help="don't save to db",
    )
    def sync_configs(units: tuple[str, ...], shared: bool, specific: bool, skip_save: bool) -> None:
        """
        Deploys the shared config.ini and worker specific config.inis to the workers.

        If neither `--shared` not `--specific` are specified, both are set to true.
        """
        logger = create_logger(
            "sync_configs", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT
        )
        units = universal_identifier_to_all_workers(units)

        if not shared and not specific:
            shared = specific = True

        def _thread_function(unit: str) -> bool:
            logger.debug(f"Syncing configs on {unit}...")
            try:
                sync_config_files(unit, shared, specific)
                return True
            except Exception as e:
                logger.error(f"Unable to connect to unit {unit}.")
                logger.debug(e, exc_info=True)
                return False

        if not skip_save:
            # save config.inis to database
            save_config_files_to_db(units, shared, specific)

        results = []
        for unit in units:
            results.append(_thread_function(unit))

        if not all(results):
            raise click.Abort()

    @pios.command("kill", short_help="kill a job(s) on workers")
    @click.argument("job", nargs=-1)
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a hostname, default is all active units",
    )
    @click.option("--all-jobs", is_flag=True, help="kill all worker jobs")
    @click.option("-y", is_flag=True, help="skip asking for confirmation")
    def kill(job: str, units: tuple[str, ...], all_jobs: bool, y: bool) -> None:
        """
        Send a SIGTERM signal to JOB. JOB can be any Pioreactor job name, like "stirring".
        Example:

        > pios kill stirring


        multiple jobs accepted:

        > pios kill stirring dosing_control


        Kill all worker jobs (i.e. this excludes leader jobs like watchdog). Ignores `job` argument.

        > pios kill --all-jobs -y


        """
        from sh import ssh  # type: ignore
        from sh import ErrorReturnCode_255  # type: ignore
        from sh import ErrorReturnCode_1  # type: ignore

        if not y:
            confirm = input(
                f"Confirm killing {str(job) if (not all_jobs) else 'all jobs'} on {units}? Y/n: "
            ).strip()
            if confirm != "Y":
                raise click.Abort()

        command = f"pio kill {' '.join(job)}"
        command += "--all-jobs" if all_jobs else ""

        logger = create_logger("CLI", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)

        def _thread_function(unit: str):
            logger.debug(f"Executing `{command}` on {unit}.")
            try:
                ssh(add_local(unit), command)
                return True

            except ErrorReturnCode_255 as e:
                logger.debug(e, exc_info=True)
                logger.error(f"Unable to connect to unit {unit}. {e.stderr.decode()}")
                return False
            except ErrorReturnCode_1 as e:
                logger.error(f"Error occurred: {e}. See logs for more.")
                logger.debug(e, exc_info=True)
                logger.debug(e.stderr, exc_info=True)
                return False

        units = universal_identifier_to_all_active_workers(units)
        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()

    @pios.command(
        name="run",
        context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
        short_help="run a job on workers",
    )
    @click.argument("job", type=click.STRING)
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a hostname, default is all active units",
    )
    @click.option("-y", is_flag=True, help="Skip asking for confirmation.")
    @click.pass_context
    def run(ctx, job: str, units: tuple[str, ...], y: bool) -> None:
        """
        Run a job on all, or specific, workers. Ex:

        > pios run stirring

        Will start stirring on all workers, after asking for confirmation.
        Each job has their own unique options:

        > pios run stirring --duty-cycle 10
        > pios run od_reading --od-angle-channel 135,0

        To specify specific units, use the `--units` keyword multiple times, ex:

        > pios run stirring --units pioreactor2 --units pioreactor3

        """
        from sh import ssh
        from sh import ErrorReturnCode_255  # type: ignore
        from sh import ErrorReturnCode_1  # type: ignore
        from shlex import quote  # https://docs.python.org/3/library/shlex.html#shlex.quote

        extra_args = list(ctx.args)

        if "unit" in extra_args:
            click.echo("Did you mean to use 'units' instead of 'unit'? Exiting.", err=True)
            raise click.Abort()

        core_command = " ".join(["pio", "run", quote(job), *extra_args])

        # pipe all output to null
        command = " ".join(["nohup", core_command, ">/dev/null", "2>&1", "&"])

        units = universal_identifier_to_all_active_workers(units)

        if not y:
            confirm = input(f"Confirm running `{core_command}` on {units}? Y/n: ").strip()
            if confirm != "Y":
                raise click.Abort()

        def _thread_function(unit: str) -> bool:
            click.echo(f"Executing `{core_command}` on {unit}.")
            try:
                ssh(add_local(unit), command)
                return True
            except ErrorReturnCode_255 as e:
                logger = create_logger("CLI", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
                logger.debug(e, exc_info=True)
                logger.error(f"Unable to connect to unit {unit}. {e.stderr.decode()}")
                return False
            except ErrorReturnCode_1 as e:
                logger = create_logger("CLI", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
                logger.error(f"Error occurred: {e}. See logs for more.")
                logger.debug(e.stderr, exc_info=True)
                return False

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()

    @pios.command(
        name="shutdown",
        short_help="shutdown Pioreactors",
    )
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a hostname, default is all active units",
    )
    @click.option("-y", is_flag=True, help="Skip asking for confirmation.")
    def shutdown(units: tuple[str, ...], y: bool) -> None:
        """
        Shutdown Pioreactor / Raspberry Pi
        """
        from sh import ssh  # type: ignore
        from sh import ErrorReturnCode_255  # type: ignore
        from sh import ErrorReturnCode_1  # type: ignore

        command = "sudo shutdown -h now"
        units = universal_identifier_to_all_workers(units)
        also_shutdown_leader = get_leader_hostname() in units
        units_san_leader = remove_leader(units)

        if not y:
            confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
            if confirm != "Y":
                raise click.Abort()

        def _thread_function(unit: str) -> bool:
            click.echo(f"Executing `{command}` on {unit}.")
            try:
                ssh(add_local(unit), command)
                return True
            except ErrorReturnCode_255 as e:
                logger = create_logger("CLI", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
                logger.debug(e, exc_info=True)
                logger.error(f"Unable to connect to unit {unit}. {e.stderr.decode()}")
                return False
            except ErrorReturnCode_1 as e:
                logger.error(f"Error occurred: {e}. See logs for more.")
                logger.debug(e.stderr, exc_info=True)
                return False

        if len(units_san_leader) > 0:
            with ThreadPoolExecutor(max_workers=len(units_san_leader)) as executor:
                executor.map(_thread_function, units_san_leader)

        # we delay shutdown leader (if asked), since it would prevent
        # executing the shutdown cmd on other workers
        if also_shutdown_leader:
            import os

            os.system(command)

    @pios.command(
        name="reboot",
        short_help="reboot Pioreactors",
    )
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a hostname, default is all active units",
    )
    @click.option("-y", is_flag=True, help="Skip asking for confirmation.")
    def reboot(units: tuple[str, ...], y: bool) -> None:
        """
        Reboot Pioreactor / Raspberry Pi
        """
        from sh import ssh  # type: ignore
        from sh import ErrorReturnCode_255  # type: ignore
        from sh import ErrorReturnCode_1  # type: ignore

        command = "sudo reboot"
        units = universal_identifier_to_all_workers(units)
        also_reboot_leader = get_leader_hostname() in units
        units_san_leader = remove_leader(units)

        if not y:
            confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
            if confirm != "Y":
                raise click.Abort()

        def _thread_function(unit: str) -> bool:
            click.echo(f"Executing `{command}` on {unit}.")
            try:
                ssh(add_local(unit), command)
                return True
            except ErrorReturnCode_255 as e:
                logger = create_logger("CLI", unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
                logger.debug(e, exc_info=True)
                logger.error(f"Unable to connect to unit {unit}. {e.stderr.decode()}")
                return False
            except ErrorReturnCode_1 as e:
                logger.error(f"Error occurred: {e}. See logs for more.")
                logger.debug(e.stderr, exc_info=True)
                return False

        if len(units_san_leader) > 0:
            with ThreadPoolExecutor(max_workers=len(units_san_leader)) as executor:
                executor.map(_thread_function, units_san_leader)

        # we delay rebooting leader (if asked), since it would prevent
        # executing the reboot cmd on other workers
        if also_reboot_leader:
            import os

            os.system(command)

    @pios.command(
        name="update-settings",
        context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
        short_help="update settings on a job on workers",
    )
    @click.argument("job", type=click.STRING)
    @click.option(
        "--units",
        multiple=True,
        default=(UNIVERSAL_IDENTIFIER,),
        type=click.STRING,
        help="specify a hostname, default is all active units",
    )
    @click.pass_context
    def update_settings(ctx, job: str, units: tuple[str, ...]) -> None:
        """

        Examples
        ---------
        > pios update-settings stirring --target_rpm 500 --units worker1
        > pios update-settings dosing_control --automation '{"type": "dosing", "automation_name": "silent", "args": {}}

        """

        exp = get_latest_experiment_name()
        extra_args = {ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)}

        if "unit" in extra_args:
            click.echo("Did you mean to use 'units' instead of 'unit'? Exiting.", err=True)
            raise click.Abort()

        assert len(extra_args) > 0

        from pioreactor.pubsub import publish

        def _thread_function(unit: str) -> bool:
            for setting, value in extra_args.items():
                publish(f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value)
            return True

        units = universal_identifier_to_all_active_workers(units)
        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        if not all(results):
            raise click.Abort()


if __name__ == "__main__":
    pios()
