# -*- coding: utf-8 -*-
"""
cmd line interface for running individual morbidostat units (including leader)

> mb run stirring
> mb run od_reading --od-angle-channel 135,0
> mb log
"""

from sh import tail
import click
import importlib
from subprocess import call
from morbidostat.whoami import am_I_leader


@click.group()
def mb():
    pass


@mb.command(name="log")
def log():
    for line in tail("-f", "/var/log/morbidostat.log", _iter=True):
        print(line)


@mb.command(name="run", context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.argument("job")
@click.option("--background", "-b", is_flag=True)
@click.pass_context
def run(ctx, job, background):

    extra_args = list(ctx.args)

    if am_I_leader():
        job = f"leader.{job}"

    if importlib.util.find_spec(f"morbidostat.background_jobs.{job}"):
        loc = f"morbidostat.background_jobs.{job}"
    elif importlib.util.find_spec(f"morbidostat.actions.{job}"):
        loc = f"morbidostat.actions.{job}"
    else:
        raise ValueError(f"Job {job} not found")

    command = ["python3", "-u", "-m", loc] + extra_args

    if background:
        command = ["nohup"] + command + ["-v", ">>", "~/morbidostat.log", "2>&1", "&"]
        print("Appending logs to ~/morbidostat.log")

    call(" ".join(command), shell=True)
    return


if __name__ == "__main__":
    mb()
