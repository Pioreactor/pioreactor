# -*- coding: utf-8 -*-
import click
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob


class NoOpJob(BackgroundJob):
    """
    A trivial background job that does nothing beyond initialization.
    """

    job_name = "noop"

    def __init__(self, unit: pt.Unit, experiment: pt.Experiment) -> None:
        super().__init__(unit=unit, experiment=experiment)


@click.command(name="noop")
def click_noop() -> None:
    """
    Start a no-op job.
    """
    with NoOpJob(unit=whoami.get_unit_name(), experiment=whoami.UNIVERSAL_EXPERIMENT) as job:
        pass
