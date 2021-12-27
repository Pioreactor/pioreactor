# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the dosing automation.


To change the automation over MQTT,

    pioreactor/<unit>/<experiment>/dosing_control/automation/set


with payload a json object with required keyword argument(s). Specify the new automation with name `"automation_name"`.


Using the CLI, specific automation values can be specified as additional options (note the underscore...) :

    > pio run dosing_control --automation-name turbidostat --volume 1.0 --target_od 3.0


"""
import time
import json
import click

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.logging import create_logger
from pioreactor.background_jobs.subjobs.alt_media_calculator import AltMediaCalculator
from pioreactor.background_jobs.subjobs.throughput_calculator import ThroughputCalculator
from pioreactor.background_jobs.utils import AutomationDict


class DosingController(BackgroundJob):

    # this is populated dynamically with subclasses of DosingAutomations in the form:
    # {
    #    DosingAutomation1.key: DosingAutomation1,
    #    ...
    # }
    # this includes plugins
    automations = {}  # type: ignore

    published_settings = {
        "automation": {"datatype": "json", "settable": True},
        "automation_name": {"datatype": "string", "settable": False},
    }

    def __init__(
        self, automation_name: str, unit: str, experiment: str, **kwargs
    ) -> None:
        super(DosingController, self).__init__(
            job_name="dosing_control", unit=unit, experiment=experiment
        )

        self.automation = AutomationDict(automation_name=automation_name, **kwargs)

        self.alt_media_calculator = AltMediaCalculator(
            unit=self.unit, experiment=self.experiment, parent=self
        )
        self.throughput_calculator = ThroughputCalculator(
            unit=self.unit, experiment=self.experiment, parent=self
        )
        self.sub_jobs = [self.alt_media_calculator, self.throughput_calculator]

        try:
            automation_class = self.automations[self.automation["automation_name"]]
        except KeyError:
            self.set_state(self.DISCONNECTED)
            raise KeyError(
                f"Unable to find automation {self.automation['automation_name']}. Available automations are {list(self.automations.keys())}"
            )

        self.logger.info(f"Starting {self.automation}.")

        try:
            self.automation_job = automation_class(
                unit=self.unit, experiment=self.experiment, **kwargs
            )
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            self.set_state(self.DISCONNECTED)
            raise e
        self.automation_name = self.automation["automation_name"]

    def set_automation(self, new_dosing_automation_json) -> None:
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.dosing_automation_job.set_state("init")
        # self.dosing_automation_job.set_state("ready")
        # because the state in MQTT is wrong.
        # OR should just bail...
        algo_metadata = AutomationDict(**json.loads(new_dosing_automation_json))

        try:
            self.automation_job.set_state("disconnected")
        except AttributeError:
            # sometimes the user will change the job too fast before the dosing job is created, let's protect against that.
            time.sleep(1)
            self.set_automation(new_dosing_automation_json)

        try:
            klass = self.automations[algo_metadata["automation_name"]]
            self.logger.info(f"Starting {algo_metadata}.")
            self.automation_job = klass(
                unit=self.unit, experiment=self.experiment, **algo_metadata
            )
            self.automation = algo_metadata
            self.automation_name = self.automation["automation_name"]
        except KeyError:
            self.logger.debug(
                f"Unable to find automation {algo_metadata['automation_name']}. Available automations are {list(self.automations.keys())}",
                exc_info=True,
            )
            self.logger.warning(
                f"Unable to find automation {algo_metadata['automation_name']}. Available automations are {list(self.automations.keys())}"
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

            for job in self.sub_jobs:
                job.set_state(job.DISCONNECTED)
            self.automation_job.set_state(self.DISCONNECTED)

        except AttributeError:
            # if disconnect is called right after starting, automation_job isn't instantiated
            pass
        finally:
            self.clear_mqtt_cache()


def start_dosing_control(
    automation_name, duration=None, skip_first_run=False, **kwargs
) -> DosingController:
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:

        kwargs["duration"] = duration
        kwargs["unit"] = unit
        kwargs["experiment"] = experiment
        kwargs["skip_first_run"] = skip_first_run
        return DosingController(automation_name, **kwargs)  # noqa: F841

    except Exception as e:
        logger = create_logger("dosing_automation")
        logger.error(e)
        logger.debug(e, exc_info=True)
        raise e


@click.command(
    name="dosing_control",
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.option(
    "--automation-name",
    default="silent",
    help="set the automation of the system: turbidostat, morbidostat, silent, etc.",
    show_default=True,
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
    help="Normally dosing will run immediately. Set this flag to wait <duration>min before executing.",
)
@click.pass_context
def click_dosing_control(ctx, automation_name, duration, skip_first_run):
    """
    Start a dosing automation
    """
    dc = start_dosing_control(
        automation_name=automation_name,
        duration=duration,
        skip_first_run=bool(skip_first_run),
        **{
            ctx.args[i][2:].replace("-", "_"): ctx.args[i + 1]
            for i in range(0, len(ctx.args), 2)
        },
    )
    dc.block_until_disconnected()
