# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the dosing automation.


To change the automation over MQTT,

    pioreactor/<unit>/<experiment>/dosing_control/automation/set


with payload a json object looking like pioreactor.structs.Automation, ex: specify the new automation with name `"automation_name"`,
 and field "type": "dosing"


Using the CLI, specific automation values can be specified as additional options (note the underscore...) :

    > pio run dosing_control --automation-name turbidostat --volume 1.0 --target_od 3.0


"""
from __future__ import annotations

import time
from typing import Optional
from typing import Union

import click

from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.structs import DosingAutomation


class DosingController(BackgroundJob):
    """

    Attributes
    ------------

    automation: pioreactor.structs.DosingAutomation
        contains metadata about the automation running
    automation_name: str
        the name of the automation running. Same as `automation.automation_name`.
    automation_job: pioreactor.available_automations.dosing.base.DosingAutomationJob
        reference to the Python object of the automation.

    """

    # `available_automations` is populated dynamically with uninitialized subclasses of DosingAutomationJobs in the form:
    # {
    #    automation_name: DosingAutomationJob1,
    #    ...
    # }
    # this includes plugins
    available_automations = {}  # type: ignore
    job_name = "dosing_control"
    published_settings = {
        "automation": {"datatype": "Automation", "settable": True},
        "automation_name": {"datatype": "string", "settable": False},
    }

    def __init__(self, unit: str, experiment: str, automation_name: str, **kwargs) -> None:
        super().__init__(unit=unit, experiment=experiment)

        try:
            automation_class = self.available_automations[automation_name]
        except KeyError:
            self.logger.error(
                f"Unable to find automation {automation_name}. Available automations are {list(self.available_automations.keys())}"
            )
            self.clean_up()
            raise KeyError(
                f"Unable to find automation {automation_name}. Available automations are {list(self.available_automations.keys())}"
            )

        self.automation = DosingAutomation(automation_name=automation_name, args=kwargs)
        self.automation_name = self.automation.automation_name
        self.logger.info(f"Starting {self.automation}.")

        try:
            self.automation_job = automation_class(
                unit=self.unit, experiment=self.experiment, **kwargs
            )
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            self.clean_up()
            raise e

    def set_automation(self, algo_metadata: DosingAutomation) -> None:
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.dosing_automation_job.set_state("init")
        # self.dosing_automation_job.set_state("ready")
        # because the state in MQTT is wrong.
        # OR should just bail...

        assert isinstance(algo_metadata, DosingAutomation)

        try:
            self.automation_job.clean_up()
        except AttributeError:
            # sometimes the user will change the job too fast before the dosing job is created, let's protect against that.
            time.sleep(1)
            self.set_automation(algo_metadata)

        try:
            klass = self.available_automations[algo_metadata.automation_name]
            self.logger.info(f"Starting {algo_metadata}.")
            self.automation_job = klass(
                unit=self.unit, experiment=self.experiment, **algo_metadata.args
            )
            self.automation = algo_metadata
            self.automation_name = self.automation.automation_name
        except KeyError:
            self.logger.debug(
                f"Unable to find automation {algo_metadata.automation_name}. Available automations are {list(self.available_automations.keys())}. Note: You need to restart this job to have access to newly-added automations.",
                exc_info=True,
            )
            self.logger.warning(
                f"Unable to find automation {algo_metadata.automation_name}. Available automations are {list(self.available_automations.keys())}. Note: You need to restart this job to have access to newly-added automations."
            )
        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_sleeping(self) -> None:
        if self.automation_job.state != self.SLEEPING:
            self.automation_job.set_state(self.SLEEPING)

    def on_ready(self) -> None:
        try:
            if self.automation_job.state != self.READY:
                self.automation_job.set_state(self.READY)
        except AttributeError:
            # attribute error occurs on first init of _control
            pass

    def on_disconnected(self) -> None:
        try:
            self.automation_job.clean_up()
        except AttributeError:
            # if disconnect is called right after starting, automation_job isn't instantiated
            pass


def start_dosing_control(
    automation_name: str,
    duration: Optional[Union[float, str]] = None,
    skip_first_run: bool = False,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    **kwargs,
) -> DosingController:
    return DosingController(
        unit=unit or whoami.get_unit_name(),
        experiment=experiment or whoami.get_latest_experiment_name(),
        automation_name=automation_name,
        duration=duration,
        skip_first_run=skip_first_run,
        **kwargs,
    )


@click.command(
    name="dosing_control",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation-name",
    help="set the automation of the system: turbidostat, morbidostat, silent, etc.",
    show_default=True,
    required=True,
)
@click.option(
    "--duration",
    default=60,
    type=float,
    help="Time, in minutes, between every monitor check",
)
@click.option(
    "--skip-first-run",
    type=click.IntRange(min=0, max=1),
    help="Normally dosing will run immediately. Set this to wait <duration>min before executing.",
)
@click.pass_context
def click_dosing_control(
    ctx: click.Context, automation_name: str, duration: float, skip_first_run: bool
) -> None:
    """
    Start a dosing automation
    """
    import os

    os.nice(1)

    dc = start_dosing_control(
        automation_name=automation_name,
        duration=duration,
        skip_first_run=bool(skip_first_run),
        **{ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    )
    dc.block_until_disconnected()
