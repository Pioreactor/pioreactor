# -*- coding: utf-8 -*-
"""
command line for running the same command on all workers,

> mba run od_reading
> mba run stirring
> mba sync
> mba kill <substring>
"""

import importlib
import concurrent
from subprocess import run as subprocess_run
import hashlib
import click

import paramiko
from morbidostat.whoami import am_I_leader, UNIVERSAL_IDENTIFIER


ALL_UNITS = ["1", "2", "3"]


def unit_to_hostname(unit):
    return f"morbidostat{unit}"


def universal_identifier_to_all_units(units):
    if units == (UNIVERSAL_IDENTIFIER,):
        return ALL_UNITS
    else:
        return units


def checksum_git(s):
    cksum_command = "cd ~/morbidostat/ && git rev-parse HEAD"
    (stdin, stdout, stderr) = s.exec_command(cksum_command)
    checksum_worker = stdout.readlines()[0].strip()
    checksum_leader = subprocess_run(cksum_command, shell=True, capture_output=True, universal_newlines=True).stdout.strip()
    assert (
        checksum_worker == checksum_leader
    ), f"checksum on git failed, {checksum_worker}, {checksum_leader}. Update leader, then try running `mba sync`"


@click.group()
def mba():
    if not am_I_leader():
        print("workers cannot run `mba` commands. Try `mb` instead.")
        import sys

        sys.exit()


@mba.command()
@click.option("--units", multiple=True, default=ALL_UNITS, type=click.STRING)
def sync(units):
    # parallelize this
    cd = "cd ~/morbidostat"
    gitp = "git pull origin master"
    setup = "sudo python3 setup.py install"
    command = " && ".join([cd, gitp, setup])

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in universal_identifier_to_all_units(units):
        print(f"Executing on {unit}...")
        s.connect(unit_to_hostname(unit), username="pi")
        (stdin, stdout, stderr) = s.exec_command(command)
        # this pass line seems to be necessary
        for line in stderr.readlines():
            pass
        checksum_git(s)
        s.close()


@mba.command()
@click.argument("process")
@click.option("--units", multiple=True, default=ALL_UNITS, type=click.STRING)
@click.option("-y", is_flag=True, help="skip asking for confirmation")
def kill(process, units, y):

    kill = f"pkill {process}"
    command = " && ".join([kill])

    if not y:
        confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in universal_identifier_to_all_units(units):
        print(f"Executing on {unit}...")
        s.connect(unit_to_hostname(unit), username="pi")
        (stdin, stdout, stderr) = s.exec_command(command)
        # this pass line seems to be necessary
        for line in stderr.readlines():
            pass
        s.close()


@mba.command(name="run", context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.argument("job")
@click.option("--units", multiple=True, default=ALL_UNITS, type=click.STRING)
@click.option("-y", is_flag=True, help="skip asking for confirmation")
@click.pass_context
def run(ctx, job, units, y):
    extra_args = list(ctx.args)

    command = ["mb", job] + extra_args + ["-b"]
    command = " ".join(command)

    if not y:
        confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    def _thread_function(unit):
        hostname = unit_to_hostname(unit)

        s = paramiko.SSHClient()
        s.load_system_host_keys()
        try:
            checksum_git(s)
        except AssertionError as e:
            print(e)
            return

        print(f"Executing on {unit}...")
        s.connect(unit_to_hostname(unit), username="pi")
        (stdin, stdout, stderr) = s.exec_command(command)
        for line in stderr.readlines():
            print(unit + ":" + line)
        s.close()

    units = universal_identifier_to_all_units(units)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(units)) as executor:
        executor.map(_thread_function, range(len(units)))

    return


if __name__ == "__main__":
    mba()
