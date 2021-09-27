# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and take action. This is the core of the dosing automation.


To change the automation over MQTT,

    pioreactor/<unit>/<experiment>/dosing_control/dosing_automation/set


with payload a json object with required keyword argument(s). Specify the new automation with name `"dosing_automation"`.


Using the CLI, specific automation values can be specified as additional options (note the underscore...) :

    > pio run dosing_control --automation turbidostat --volume 1.0 --target_od 3.0


"""
import time
import json
import click

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.logging import create_logger
from pioreactor.background_jobs.subjobs.alt_media_calculator import AltMediaCalculator
from pioreactor.background_jobs.subjobs.throughput_calculator import ThroughputCalculator


class DosingController(BackgroundJob):

    # this is populated dynamically with subclasses of DosingAutomations in the form:
    # {DosingAutomation.key: DosingAutomation ... }
    # this includes plugins
    automations = {}

    published_settings = {"dosing_automation": {"datatype": "string", "settable": True}}

    def __init__(self, dosing_automation, unit=None, experiment=None, **kwargs):
        super(DosingController, self).__init__(
            job_name="dosing_control", unit=unit, experiment=experiment
        )

        self.dosing_automation = dosing_automation

        self.alt_media_calculator = AltMediaCalculator(
            unit=self.unit, experiment=self.experiment, parent=self
        )
        self.throughput_calculator = ThroughputCalculator(
            unit=self.unit, experiment=self.experiment, parent=self
        )
        self.sub_jobs = [self.alt_media_calculator, self.throughput_calculator]

        # this should be a subjob, but it doesn't really fit
        # because if I append it to the list, it needs to be garbage collected manually
        # when I switch automations.
        # some better system of keep tracking of subjobs is needed.
        self.dosing_automation_job = self.automations[self.dosing_automation](
            unit=self.unit, experiment=self.experiment, **kwargs
        )

    def set_dosing_automation(self, new_dosing_automation_json):
        # TODO: this needs a better rollback. Ex: in except, something like
        # self.dosing_automation_job.set_state("init")
        # self.dosing_automation_job.set_state("ready")
        # [ ] write tests
        # OR should just bail...
        algo_init = json.loads(new_dosing_automation_json)

        try:
            self.dosing_automation_job.set_state("disconnected")
        except AttributeError:
            # sometimes the user will change the job too fast before the dosing job is created, let's protect against that.
            time.sleep(1)
            self.set_dosing_automation(new_dosing_automation_json)

        try:
            self.dosing_automation_job = self.automations[algo_init["dosing_automation"]](
                unit=self.unit, experiment=self.experiment, **algo_init
            )
            self.dosing_automation = algo_init["dosing_automation"]

        except Exception as e:
            self.logger.debug(f"Change failed because of {str(e)}", exc_info=True)
            self.logger.warning(f"Change failed because of {str(e)}")

    def on_sleeping(self):
        if self.dosing_automation_job.state != self.SLEEPING:
            self.dosing_automation_job.set_state(self.SLEEPING)

    def on_ready(self):
        try:
            if self.dosing_automation_job.state != self.READY:
                self.dosing_automation_job.set_state(self.READY)
        except AttributeError:
            # attribute error occurs on first init of _control
            pass

    def on_disconnect(self):
        try:

            for job in self.sub_jobs:
                job.set_state(job.DISCONNECTED)

            self.dosing_automation_job.set_state(self.DISCONNECTED)
        except AttributeError:
            # if disconnect is called right after starting, dosing_automation_job isn't instantiated
            pass
        finally:
            self.clear_mqtt_cache()


def run(automation=None, duration=None, skip_first_run=False, **kwargs):
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:

        kwargs["duration"] = duration
        kwargs["unit"] = unit
        kwargs["experiment"] = experiment
        kwargs["skip_first_run"] = skip_first_run
        return DosingController(automation, **kwargs)  # noqa: F841

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
    "--automation",
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
    is_flag=True,
    help="Normally dosing will run immediately. Set this flag to wait <duration>min before executing.",
)
@click.pass_context
def click_dosing_control(ctx, automation, duration, skip_first_run):
    """
    Start a dosing automation
    """
    dc = run(
        automation=automation,
        duration=duration,
        skip_first_run=skip_first_run,
        **{ctx.args[i][2:]: ctx.args[i + 1] for i in range(0, len(ctx.args), 2)},
    )
    dc.block_until_disconnected()
