# -*- coding: utf-8 -*-
"""
command line for running the same command on all workers,

> mba od_reading
> mba stirring
> mba sync
> mba kill
"""

import importlib
from subprocess import run
import hashlib
import click

import paramiko
from morbidostat.whoami import am_I_leader

UNITS = ["morbidostat1", "morbidostat2", "morbidostat3"]


def checksum_git(s):
    cksum_command = "cd ~/morbidostat/ && git rev-parse HEAD"
    (stdin, stdout, stderr) = s.exec_command(cksum_command)
    checksum_worker = stdout.readlines()[0].strip()
    checksum_leader = run(cksum_command, shell=True, capture_output=True, universal_newlines=True).stdout.strip()
    assert (
        checksum_worker == checksum_leader
    ), f"checksum on git failed, {checksum_worker}, {checksum_leader}. Update leader, then try running `mba sync`"


def sync_workers(units, y, extra_args):
    # parallelize thisF
    cd = "cd ~/morbidostat"
    gitp = "git pull origin master"
    setup = "sudo python3 setup.py install"
    command = " && ".join([cd, gitp, setup])

    if not y:
        confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in units:
        print(f"Executing on {unit}...")
        s.connect(unit, username="pi")
        (stdin, stdout, stderr) = s.exec_command(command)
        # this pass line seems to be necessary
        for line in stderr.readlines():
            pass
        checksum_git(s)
        s.close()


def kill_workers(units, y, extra_args):

    kill = "pkill python"
    command = " && ".join([kill])

    if not y:
        confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in units:
        print(f"Executing on {unit}...")
        s.connect(unit, username="pi")
        (stdin, stdout, stderr) = s.exec_command(command)
        # this pass line seems to be necessary
        for line in stderr.readlines():
            pass
        s.close()


def run_mb_command(job, units, y, extra_args):
    extra_args = list(extra_args)

    command = ["mb", job] + extra_args + ["-b"]
    command = " ".join(command)

    if not y:
        confirm = input(f"Confirm running `{command}` on {units}? Y/n: ").strip()
        if confirm != "Y":
            return

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in units:
        s.connect(unit, username="pi")

        try:
            checksum_git(s)
        except AssertionError as e:
            print(e)
            return
        s.close()

    for unit in units:
        print(f"Executing on {unit}...")
        s.connect(unit, username="pi")
        (stdin, stdout, stderr) = s.exec_command(command)
        for line in stderr.readlines():
            print(unit + ":" + line)
        s.close()

    return


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("job")
@click.option("-y", is_flag=True, help="skip asking for confirmation")
@click.option("--units", multiple=True, default=UNITS, type=click.STRING)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def cli(job, y, units, extra_args):
    if not am_I_leader():
        print("workers cannot run morbidostat-all commands. Try `mb` instead.")
        return

    if job == "sync":
        return sync_workers(units, y, extra_args)
    elif job == "kill":
        return kill_workers(units, y, extra_args)
    else:
        return run_mb_command(job, units, y, extra_args)


if __name__ == "__main__":
    cli()
