# -*- coding: utf-8 -*-
"""
command line for running the same command on all workers,

> pios run od_reading
> pios run stirring
> pios sync
> pios kill <substring>
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import click

from pioreactor.config import config
from pioreactor.config import get_active_workers_in_inventory
from pioreactor.config import get_leader_hostname
from pioreactor.logging import create_logger
from pioreactor.utils.timing import current_utc_time
from pioreactor.whoami import am_I_leader
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_IDENTIFIER


def universal_identifier_to_all_active_workers(units: tuple[str, ...]) -> tuple[str, ...]:
    if units == (UNIVERSAL_IDENTIFIER,):
        units = get_active_workers_in_inventory()
    return units


def add_leader(units: tuple[str, ...]) -> tuple[str, ...]:
    leader = get_leader_hostname()
    if leader not in units:
        units = units + (leader,)
    return units


def save_config_files_to_db(units: tuple[str, ...], shared: bool, specific: bool) -> None:
    import sqlite3

    conn = sqlite3.connect(config["storage"]["database"])
    cur = conn.cursor()

    timestamp = current_utc_time()
    sql = "INSERT INTO config_files(timestamp,filename,data) VALUES(?,?,?)"

    if specific:
        for unit in units:
            with open(f"/home/pioreactor/.pioreactor/config_{unit}.ini") as f:
                cur.execute(sql, (timestamp, f"config_{unit}.ini", f.read()))

    if shared:
        with open("/home/pioreactor/.pioreactor/config.ini") as f:
            cur.execute(sql, (timestamp, "config.ini", f.read()))

    conn.commit()
    conn.close()


def sync_config_files(ftp_client, unit: str, shared: bool, specific: bool) -> None:
    """
    Moves

    1. the config.ini (if shared is True)
    2. config_{unit}.ini to the remote Pioreactor (if specific is True)

    Note: this function occurs in a thread
    """
    # move the global config.ini
    # there was a bug where if the leader == unit, the config.ini would get wiped
    if (get_leader_hostname() != unit) and shared:
        ftp_client.put(
            localpath="/home/pioreactor/.pioreactor/config.ini",
            remotepath="/home/pioreactor/.pioreactor/config.ini",
        )

    # move the specific unit config.ini
    if specific:
        try:
            ftp_client.put(
                localpath=f"/home/pioreactor/.pioreactor/config_{unit}.ini",
                remotepath="/home/pioreactor/.pioreactor/unit_config.ini",
            )
        except Exception as e:
            click.echo(
                f"Did you forget to create a config_{unit}.ini to deploy to {unit}?",
                err=True,
            )
            raise e

    ftp_client.close()
    return


@click.group()
def pios() -> None:
    """
    Command each of the worker Pioreactors with the `pios` command.

    See full documentation here: https://docs.pioreactor.com/user_guide/Advanced/Command%20line%20interface#leader-only-commands-to-control-workers

    Report errors or feedback here: https://github.com/Pioreactor/pioreactor/issues
    """
    import sys

    if not am_I_leader():
        click.echo("workers cannot run `pios` commands. Try `pio` instead.", err=True)
        sys.exit(1)

    if len(get_active_workers_in_inventory()) == 0:
        logger = create_logger(
            "CLI", unit=get_unit_name(), experiment=get_latest_experiment_name()
        )
        logger.warning(
            "No active workers. See `network.inventory` section in config.ini."
        )
        sys.exit(1)


@pios.command("update", short_help="update PioreactorApp on workers")
@click.option(
    "--units",
    multiple=True,
    default=(UNIVERSAL_IDENTIFIER,),
    type=click.STRING,
    help="specify a Pioreactor name, default is all active units",
)
@click.option("-b", "--branch", help="update to the github branch")
def update(units: tuple[str, ...], branch: Optional[str]) -> None:
    """
    Pulls and installs the latest code
    """
    import paramiko  # type: ignore

    logger = create_logger(
        "update", unit=get_unit_name(), experiment=get_latest_experiment_name()
    )

    if branch is not None:
        command = f"pio update --app -b {branch}"
    else:
        command = "pio update --app"

    def _thread_function(unit: str):
        logger.debug(f"Executing `{command}` on {unit}...")
        try:

            with paramiko.SSHClient() as client:
                client.load_system_host_keys()
                client.connect(unit, username="pioreactor", compress=True)

                (stdin, stdout, stderr) = client.exec_command(command)
                for line in stderr.readlines():
                    pass

            return True

        except Exception as e:
            logger.error(f"Unable to connect to unit {unit}.")
            logger.debug(e, exc_info=True)
            return False

    units = universal_identifier_to_all_active_workers(units)
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        results = executor.map(_thread_function, units)

    if not all(results):
        sys.exit(1)


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
    import paramiko

    logger = create_logger(
        "install_plugin", unit=get_unit_name(), experiment=get_latest_experiment_name()
    )

    command = f"pio install-plugin {plugin}"

    def _thread_function(unit: str):
        logger.debug(f"Executing `{command}` on {unit}...")
        try:
            with paramiko.SSHClient() as client:
                client.load_system_host_keys()
                client.connect(unit, username="pioreactor", compress=True)

                (stdin, stdout, stderr) = client.exec_command(command)
                for line in stderr.readlines():
                    pass

            return True

        except Exception as e:
            logger.error(f"Unable to connect to unit {unit}.")
            logger.debug(e, exc_info=True)
            return False

    units = add_leader(universal_identifier_to_all_active_workers(units))
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        results = executor.map(_thread_function, units)

    if not all(results):
        sys.exit(1)


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
    import paramiko

    logger = create_logger(
        "uninstall_plugin", unit=get_unit_name(), experiment=get_latest_experiment_name()
    )

    command = f"pio uninstall-plugin {plugin}"

    def _thread_function(unit: str):
        logger.debug(f"Executing `{command}` on {unit}...")
        try:

            with paramiko.SSHClient() as client:
                client.load_system_host_keys()
                client.connect(unit, username="pioreactor", compress=True)

                (stdin, stdout, stderr) = client.exec_command(command)
                for line in stderr.readlines():
                    pass

            return True

        except Exception as e:
            logger.error(f"Unable to connect to unit {unit}.")
            logger.debug(e, exc_info=True)
            return False

    units = add_leader(universal_identifier_to_all_active_workers(units))
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        results = executor.map(_thread_function, units)

    if not all(results):
        sys.exit(1)


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
def sync_configs(units: tuple[str, ...], shared: bool, specific: bool) -> None:
    """
    Deploys the shared config.ini and worker specific config.inis to the workers.

    If neither `--shared` not `--specific` are specified, both are set to true.
    """
    import paramiko

    logger = create_logger(
        "sync_configs", unit=get_unit_name(), experiment=get_latest_experiment_name()
    )
    units = universal_identifier_to_all_active_workers(units)

    if not shared and not specific:
        shared = specific = True

    def _thread_function(unit: str) -> bool:
        logger.debug(f"Syncing configs on {unit}...")
        try:
            with paramiko.SSHClient() as client:
                client.load_system_host_keys()
                client.connect(unit, username="pioreactor", compress=True)

                with client.open_sftp() as ftp_client:
                    sync_config_files(ftp_client, unit, shared, specific)

            return True
        except Exception as e:
            logger.error(f"Unable to connect to unit {unit}.")
            logger.debug(e, exc_info=True)
            return False

    # save config.inis to database
    save_config_files_to_db(units, shared, specific)

    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        results = executor.map(_thread_function, units)

    if not all(results):
        sys.exit(1)


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

    > pios kill --all


    """
    from sh import ssh  # type: ignore

    if not y:
        confirm = input(
            f"Confirm killing {str(job) if (not all_jobs) else 'all jobs'} on {units}? Y/n: "
        ).strip()
        if confirm != "Y":
            return

    command = f"pio kill {' '.join(job)}"
    command += "--all-jobs" if all_jobs else ""

    logger = create_logger(
        "CLI", unit=get_unit_name(), experiment=get_latest_experiment_name()
    )

    def _thread_function(unit: str):
        logger.debug(f"Executing `{command}` on {unit}.")
        try:
            ssh(unit, command)
            if all_jobs:  # tech debt
                ssh(
                    unit,
                    "pio run led_intensity --A 0 --B 0 --C 0 --D 0 --no-log",
                )
            return True

        except Exception as e:
            logger.debug(e, exc_info=True)
            logger.error(f"Unable to connect to unit {unit}.")
            return False

    units = universal_identifier_to_all_active_workers(units)
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        results = executor.map(_thread_function, units)

    if not all(results):
        sys.exit(1)


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
    from shlex import quote  # https://docs.python.org/3/library/shlex.html#shlex.quote

    extra_args = list(ctx.args)

    if "unit" in extra_args:
        click.echo("Did you mean to use 'units' instead of 'unit'? Exiting.", err=True)
        sys.exit(1)

    core_command = " ".join(["pio", "run", quote(job), *extra_args])

    # pipe all output to null
    command = " ".join(["nohup", core_command, ">/dev/null", "2>&1", "&"])

    if not y:
        confirm = input(f"Confirm running `{core_command}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    def _thread_function(unit: str) -> bool:
        click.echo(f"Executing `{core_command}` on {unit}.")
        try:
            ssh(unit, command)
            return True
        except Exception as e:
            logger = create_logger(
                "CLI", unit=get_unit_name(), experiment=get_latest_experiment_name()
            )
            logger.debug(e, exc_info=True)
            logger.error(f"Unable to connect to unit {unit}.")
            return False

    units = universal_identifier_to_all_active_workers(units)
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        results = executor.map(_thread_function, units)

    if not all(results):
        sys.exit(1)


@pios.command(
    name="reboot",
    short_help="reboot workers",
)
@click.option(
    "--units",
    multiple=True,
    default=(UNIVERSAL_IDENTIFIER,),
    type=click.STRING,
    help="specify a hostname, default is all active units",
)
@click.option("-y", is_flag=True, help="Skip asking for confirmation.")
@click.pass_context
def reboot(units: tuple[str, ...], y: bool) -> None:
    """
    Reboot Pioreactor / Raspberry Pi
    """
    from sh import ssh

    # pipe all output to null
    command = " ".join(["sudo", "reboot"])

    if not y:
        confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    def _thread_function(unit: str) -> bool:
        # don't run on leader.
        if unit == get_unit_name():
            click.echo(f"Skipping {unit}.")
            return True

        click.echo(f"Executing `{command}` on {unit}.")
        try:
            ssh(unit, command)
            return True
        except Exception as e:
            logger = create_logger(
                "CLI", unit=get_unit_name(), experiment=get_latest_experiment_name()
            )
            logger.debug(e, exc_info=True)
            logger.error(f"Unable to connect to unit {unit}.")
            return False

    units = universal_identifier_to_all_active_workers(units)
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        results = executor.map(_thread_function, units)

    if not all(results):
        sys.exit(1)


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
        sys.exit(1)

    assert len(extra_args) > 0

    from pioreactor.pubsub import publish

    def _thread_function(unit: str) -> bool:
        for (setting, value) in extra_args.items():
            publish(f"pioreactor/{unit}/{exp}/{job}/{setting}/set", value)
        return True

    units = universal_identifier_to_all_active_workers(units)
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        results = executor.map(_thread_function, units)

    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    pios()
