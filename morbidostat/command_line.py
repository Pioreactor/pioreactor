# -*- coding: utf-8 -*-
# command line
import click
import importlib


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("job")
@click.option("--background", "-b", is_flag=True)
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def cli(job, background, extra_args):
    from subprocess import Popen, call, CalledProcessError

    extra_args = list(extra_args)

    if importlib.util.find_spec(f"morbidostat.background_jobs.{job}"):
        loc = f"morbidostat.background_jobs.{job}"
    else:
        loc = f"morbidostat.actions.{job}"

    command = ["python3", "-u", "-m", loc] + extra_args

    if background:
        command = ["nohup"] + command + ["-v", ">>", "morbidostat.log", "2>&1", "&"]
        print("Appending logs to morbidostat.log")

    call(" ".join(command), shell=True)


if __name__ == "__main__":
    cli()
