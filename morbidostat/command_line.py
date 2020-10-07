# -*- coding: utf-8 -*-
# command line
import click
import morbidostat
import importlib


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.argument("job")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def cli(job, extra_args):
    from subprocess import run, CalledProcessError

    extra_args = list(extra_args)

    if importlib.util.find_spec(f"morbidostat.background_jobs.{job}"):
        run(["python3", "-m", f"morbidostat.background_jobs.{job}"] + extra_args)
    else:
        run(["python3", "-m", f"morbidostat.actions.{job}"] + extra_args)


if __name__ == "__main__":
    cli()
