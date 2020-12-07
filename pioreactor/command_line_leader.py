# -*- coding: utf-8 -*-
"""
command line for running the same command on all workers,

> pios run od_reading
> pios run stirring
> pios sync
> pios kill <substring>
"""
from concurrent.futures import ThreadPoolExecutor

import click

from pioreactor.whoami import am_I_leader, UNIVERSAL_IDENTIFIER
from pioreactor.config import get_units_and_ips

ALL_WORKER_JOBS = [
    "stirring",
    "growth_rate_calculating",
    "io_controlling",
    "stirring",
    "od_reading",
    "add_alt_media",
    "add_media",
    "remove_waste",
    "od_normalization",
]


def unit_to_hostname(unit):
    return f"pioreactor{unit}"


def universal_identifier_to_all_units(units):
    if units == (UNIVERSAL_IDENTIFIER,):
        return list(get_units_and_ips().keys())
    else:
        return list(map(unit_to_hostname, units))


def checksum_git(s):
    from subprocess import run as subprocess_run

    cksum_command = "cd ~/pioreactor/ && git rev-parse HEAD"
    (stdin, stdout, stderr) = s.exec_command(cksum_command)
    checksum_worker = stdout.readlines()[0].strip()
    checksum_leader = subprocess_run(
        cksum_command, shell=True, capture_output=True, universal_newlines=True
    ).stdout.strip()
    assert (
        checksum_worker == checksum_leader
    ), f"checksum on git failed, {checksum_worker}, {checksum_leader}. Update leader, then try running `pios sync`"


def sync_config_files(client, unit):
    # occurs in a thread
    ftp_client = client.open_sftp()

    # move the global config.ini

    # due to permissions, we can't ftp to /etc/, so we move to where we can
    # and then use `sudo` to move it.
    ftp_client.put("/home/pi/.pioreactor/config.ini", "/home/pi/.pioreactor/config.ini")

    # move the local config.ini
    try:
        ftp_client.put(
            f"/home/pi/.pioreactor/config{unit}.ini",
            "/home/pi/.pioreactor/unit_config.ini",
        )
    except Exception as e:
        print(f"Did you forget to create a config{unit}.ini to ship to pioreactor{unit}.")
        raise e

    ftp_client.close()
    return


@click.group()
def pios():
    """
    Command each of the worker pioreactors with the `pios` command
    """
    if not am_I_leader():
        print("workers cannot run `pios` commands. Try `pio` instead.")

        import sys

        sys.exit(0)


@pios.command("sync", short_help="sync code and config")
@click.option(
    "--units", multiple=True, default=(UNIVERSAL_IDENTIFIER,), type=click.STRING
)
def sync(units):
    """
    Deploys the config.inis from the leader to the workers, pulls and installs the latest code from Github to the
    workers.
    """

    import paramiko

    cd = "cd ~/pioreactor"
    gitp = "git pull origin master"
    setup = "sudo python3 setup.py install"
    command = " && ".join([cd, gitp, setup])

    def _thread_function(hostname):
        print(f"Executing on {hostname}...")
        try:

            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.connect(hostname, username="pi")

            (stdin, stdout, stderr) = client.exec_command(command)
            for line in stderr.readlines():
                pass

            try:
                checksum_git(client)
            except AssertionError as e:
                print(e)
                return

            sync_config_files(client, hostname)

            client.close()

        except Exception:
            import traceback

            print(f"hostname={hostname}")
            traceback.print_exc()

    hostnames = universal_identifier_to_all_units(units)
    with ThreadPoolExecutor(max_workers=len(hostnames)) as executor:
        executor.map(_thread_function, hostnames)


@pios.command(name="sync-configs", short_help="sync config")
@click.option(
    "--units", multiple=True, default=(UNIVERSAL_IDENTIFIER,), type=click.STRING
)
def sync_configs(units):
    """
    Deploys the leader's config.inis to the workers.
    """

    import paramiko

    def _thread_function(hostname):
        print(f"Executing on {hostname}...")
        try:

            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.connect(hostname, username="pi")

            sync_config_files(client, hostname)

            client.close()
        except Exception:
            import traceback

            print(f"hostname={hostname}")
            traceback.print_exc()

    hostnames = universal_identifier_to_all_units(units)
    with ThreadPoolExecutor(max_workers=len(hostnames)) as executor:
        executor.map(_thread_function, hostnames)


@pios.command("kill", short_help="kill a job on workers")
@click.argument("process")
@click.option(
    "--units", multiple=True, default=(UNIVERSAL_IDENTIFIER,), type=click.STRING
)
@click.option("-y", is_flag=True, help="skip asking for confirmation")
def kill(process, units, y):
    """
    send a SIGTERM signal to PROCESS. PROCESS can be any job name or "python" (the
    later will clear all jobs, but maybe other python scripts too.)

    """
    from sh import ssh

    if not y:
        confirm = input(f"Confirm killing `{process}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    kill = f"pkill -f {process}"
    command = " && ".join([kill])

    def _thread_function(unit):
        hostname = unit_to_hostname(unit)

        print(f"Executing on {unit}...")
        ssh(hostname, command)

    units = universal_identifier_to_all_units(units)
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        executor.map(_thread_function, units)


@pios.command(
    name="run",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
    short_help="run a job on workers",
)
@click.argument("job", type=click.Choice(ALL_WORKER_JOBS, case_sensitive=True))
@click.option(
    "--units", multiple=True, default=(UNIVERSAL_IDENTIFIER,), type=click.STRING
)
@click.option("-y", is_flag=True, help="skip asking for confirmation")
@click.pass_context
def run(ctx, job, units, y):
    from sh import ssh

    extra_args = list(ctx.args)

    command = ["nohup", "pio", "run", job, *extra_args, ">/dev/null", "2>&1", "&"]
    command = " ".join(command)

    if not y:
        confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    def _thread_function(unit):
        hostname = unit_to_hostname(unit)
        ssh(hostname, command)

    units = universal_identifier_to_all_units(units)
    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        executor.map(_thread_function, units)

    return


if __name__ == "__main__":
    pios()
