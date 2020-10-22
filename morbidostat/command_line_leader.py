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

UNITS = ["morbidostat2", "morbidostat3"]


def checksum_config_file(s):
    cksum_command = "cksum ~/morbidostat/morbidostat/config.ini"
    (stdin, stdout, stderr) = s.exec_command(cksum_command)
    checksum_worker = stdout.readlines()[0].split(" ")[0].strip()
    checksum_leader = run(cksum_command, shell=True, capture_output=True, universal_newlines=True).stdout.strip().split(" ")[0]
    assert (
        checksum_worker == checksum_leader
    ), f"checksum on config.ini failed, {checksum_worker}, {checksum_leader}. Try running `mba sync` first."


def checksum_git(s):
    cksum_command = "cd ~/morbidostat/ && git rev-parse HEAD"
    (stdin, stdout, stderr) = s.exec_command(cksum_command)
    checksum_worker = stdout.readlines()[0].strip()
    checksum_leader = run(cksum_command, shell=True, capture_output=True, universal_newlines=True).stdout.strip()
    assert (
        checksum_worker == checksum_leader
    ), f"checksum on git failed, {checksum_worker}, {checksum_leader}. Update leader, then try running `mba sync`"


def sync_workers(extra_args):
    cd = "cd ~/morbidostat"
    gitp = "git pull origin master"
    sync = "sudo python3 sync.py install"
    command = " && ".join([cd, gitp, sync])

    confirm = input(f"Confirm running `{command}` on {UNITS}? Y/n: ").strip()
    if confirm != "Y":
        return

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in UNITS:
        print(f"Executing on {unit}...")
        s.connect(unit, username="pi")
        (stdin, stdout, stderr) = s.exec_command(command)
        # this pass line seems to be necessary
        for line in stderr.readlines():
            pass
        checksum_config_file(s)
        checksum_git(s)
        s.close()


def kill_workers(extra_args):
    kill = "pkill python"
    command = " && ".join([kill])

    confirm = input(f"Confirm running `{command}` on {UNITS}? Y/n: ").strip()
    if confirm != "Y":
        return

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in UNITS:
        print(f"Executing on {unit}...")
        s.connect(unit, username="pi")
        (stdin, stdout, stderr) = s.exec_command(command)
        # this pass line seems to be necessary
        for line in stderr.readlines():
            pass
        s.close()


def run_mb_command(job, extra_args):
    extra_args = list(extra_args)

    command = ["mb", job] + extra_args + ["-b"]
    command = " ".join(command)

    confirm = input(f"Confirm running `{command}` on {UNITS}? Y/n: ").strip()
    if confirm != "Y":
        return

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in UNITS:
        s.connect(unit, username="pi")

        try:
            checksum_config_file(s)
            checksum_git(s)
        except AssertionError as e:
            print(e)
            continue

        (stdin, stdout, stderr) = s.exec_command(command)
        for line in stderr.readlines():
            print(unit + ":" + line)
        s.close()

    return


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("job")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def cli(job, extra_args):
    if not am_I_leader():
        print("workers cannot run morbidostat-all commands. Try `mb` instead.")
        return

    if job == "sync":
        return sync_workers(extra_args)
    elif job == "kill":
        return kill_workers(extra_args)
    else:
        return run_mb_command(job, extra_args)


if __name__ == "__main__":
    cli()
