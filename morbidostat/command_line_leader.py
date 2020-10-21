# -*- coding: utf-8 -*-
# command line for running the same command on all workers,
# > mba od_reading
# > mba stirring
import importlib
import click
import paramiko
from morbidostat.whoami import am_I_leader


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("job")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def cli(job, extra_args):

    if not am_I_leader():
        print("workers are not suppose to run morbidostat-all commands.")
        return

    extra_args = list(extra_args)

    command = ["mb", job] + extra_args + ["-b"]
    print(" ".join(command))

    s = paramiko.SSHClient()
    s.load_system_host_keys()

    for unit in ["morbidostat1", "morbidostat2", "morbidostat3"]:
        s.connect(unit, username="pi")
        (stdin, stdout, stderr) = s.exec_command("touch here")
        for line in stdout.readlines():
            print(line)
        s.close()

    return


if __name__ == "__main__":
    cli()
