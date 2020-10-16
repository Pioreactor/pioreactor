# -*- coding: utf-8 -*-
# command line
import click
import importlib
from subprocess import call
from morbidostat.whoami import am_I_leader


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("job")
@click.option("--background", "-b", is_flag=True)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def cli(job, background, extra_args):

    if am_I_leader():
        print("leader is not suppose to run morbidostat commands.")
        return

    extra_args = list(extra_args)

    if importlib.util.find_spec(f"morbidostat.background_jobs.{job}"):
        loc = f"morbidostat.background_jobs.{job}"
    elif importlib.util.find_spec(f"morbidostat.actions.{job}"):
        loc = f"morbidostat.actions.{job}"
    else:
        raise ValueError(f"Job {job} not found")

    command = ["python3", "-u", "-m", loc] + extra_args

    if background:
        command = ["nohup"] + command + ["-v", ">>", "morbidostat.log", "2>&1", "&"]
        print("Appending logs to morbidostat.log")

    call(" ".join(command), shell=True)
    return


if __name__ == "__main__":
    cli()
