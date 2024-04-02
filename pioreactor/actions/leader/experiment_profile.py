# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from sched import scheduler
from typing import Callable
from typing import Optional

import click
from msgspec.json import encode
from msgspec.yaml import decode

from pioreactor.cluster_management import get_active_workers_in_experiment
from pioreactor.config import leader_address
from pioreactor.experiment_profiles import profile_struct as struct
from pioreactor.logging import create_logger
from pioreactor.logging import CustomLogger
from pioreactor.mureq import put
from pioreactor.pubsub import publish
from pioreactor.utils import ClusterJobManager
from pioreactor.utils import managed_lifecycle
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name

bool_expression = str | bool


def wrap_in_try_except(func, logger: CustomLogger) -> Callable:
    def inner_function(*args, **kwargs) -> None:
        try:
            func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Error in action: {e}")

    return inner_function


def is_bracketed_expression(value: str) -> bool:
    import re

    pattern = r"\${{(.*?)}}"
    return bool(re.search(pattern, str(value)))


def strip_expression_brackets(value: str) -> str:
    import re

    pattern = r"\${{(.*?)}}"
    match = re.search(pattern, value)
    assert match is not None
    return match.group(1)


def evaluate_options(options: dict, unit: str) -> dict:
    """
    Users can provide options like {'target_rpm': '${{ bioreactor_A:stirring:target_rpm + 10 }}'}, and the latter
    should be evaluated
    """
    from pioreactor.experiment_profiles.parser import parse_profile_expression

    options_expressed = {}
    for key, value in options.items():
        if is_bracketed_expression(value):
            expression = strip_expression_brackets(value)
            # replace :: placeholder with unit
            expression = expression.replace("::", f"{unit}:", 1)
            options_expressed[key] = parse_profile_expression(expression)
        else:
            options_expressed[key] = value
    return options_expressed


def evaluate_bool_expression(bool_expression: bool_expression, unit: str) -> bool:
    from pioreactor.experiment_profiles.parser import parse_profile_expression_to_bool

    if isinstance(bool_expression, bool):
        return bool_expression

    if is_bracketed_expression(bool_expression):
        bool_expression = strip_expression_brackets(bool_expression)

    # replace :: placeholder with unit
    bool_expression = bool_expression.replace("::", f"{unit}:", 1)

    # bool_expression is a str
    return parse_profile_expression_to_bool(bool_expression)


def check_syntax_of_bool_expression(bool_expression: bool_expression) -> bool:
    from pioreactor.experiment_profiles.parser import check_syntax

    if isinstance(bool_expression, bool):
        return True

    if is_bracketed_expression(bool_expression):
        bool_expression = strip_expression_brackets(bool_expression)

    # in a common expressions, users can use ::word:work which is technically not allowed. For checking, we replace with garbage
    bool_expression = bool_expression.replace("::", "dummy:", 1)

    return check_syntax(bool_expression)


def _led_intensity_hack(action: struct.Action) -> struct.Action:
    # we do this hack because led_intensity doesn't really behave like a background job, but its useful to
    # treat it as one.
    match action:
        case struct.Log(_, _, _):
            # noop
            return action

        case struct.Start(_, _, _, _):
            # noop
            return action

        case struct.Repeat(_, _, _, _, _, _):
            # noop
            return action

        case struct.Pause(hours, if_) | struct.Stop(hours, if_):
            options = {"A": 0, "B": 0, "C": 0, "D": 0}
            return struct.Start(hours, if_, options, [])

        case struct.Update(hours, if_, options):
            return struct.Start(hours, if_, options, [])

        case _:
            raise ValueError()


def get_simple_priority(action: struct.Action):
    match action:
        case struct.Start():
            return 0
        case struct.Stop():
            return 1
        case struct.Pause():
            return 2
        case struct.Resume():
            return 3
        case struct.Update():
            return 4
        case struct.Repeat():
            return 6
        case struct.Log():
            return 10
        case _:
            raise ValueError(f"Not a valid action: {action}")


def wrapped_execute_action(
    unit: str,
    experiment: str,
    job_name: str,
    logger: CustomLogger,
    schedule: scheduler,
    action: struct.Action,
    dry_run: bool = False,
) -> Callable[..., None]:
    # hack...
    if job_name == "led_intensity":
        action = _led_intensity_hack(action)

    match action:
        case struct.Start(_, if_, options, args):
            return start_job(unit, experiment, job_name, options, args, dry_run, if_, logger)

        case struct.Pause(_, if_):
            return pause_job(unit, experiment, job_name, dry_run, if_, logger)

        case struct.Resume(_, if_):
            return resume_job(unit, experiment, job_name, dry_run, if_, logger)

        case struct.Stop(_, if_):
            return stop_job(unit, experiment, job_name, dry_run, if_, logger)

        case struct.Update(_, if_, options):
            return update_job(unit, experiment, job_name, options, dry_run, if_, logger)

        case struct.Log(_, options, if_):
            return log(unit, experiment, job_name, options, dry_run, if_, logger)

        case struct.Repeat(_, if_, repeat_every_hours, while_, max_hours, actions):
            return repeat(
                unit,
                experiment,
                job_name,
                dry_run,
                if_,
                logger,
                action,
                while_,
                repeat_every_hours,
                max_hours,
                actions,
                schedule,
            )

        case _:
            raise ValueError(f"Not a valid action: {action}")


def chain_functions(*funcs: Callable[[], None]) -> Callable[[], None]:
    def combined_function() -> None:
        for func in funcs:
            func()

    return combined_function


def common_wrapped_execute_action(
    experiment: str,
    job_name: str,
    logger: CustomLogger,
    schedule: scheduler,
    action: struct.Action,
    dry_run: bool = False,
) -> Callable[..., None]:
    actions_to_execute = []
    for worker in get_active_workers_in_experiment(experiment):
        actions_to_execute.append(
            wrapped_execute_action(worker, experiment, job_name, logger, schedule, action, dry_run)
        )

    return chain_functions(*actions_to_execute)


def repeat(
    unit: str,
    experiment: str,
    job_name: str,
    dry_run: bool,
    if_: Optional[bool_expression],
    logger: CustomLogger,
    repeat_action: struct.Repeat,
    while_: Optional[bool_expression],
    repeat_every_hours: float,
    max_hours: Optional[float],
    actions: list[struct.ActionWithoutRepeat],
    schedule: scheduler,
):
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            return

        if ((if_ is None) or evaluate_bool_expression(if_, unit)) and (
            ((while_ is None) or evaluate_bool_expression(while_, unit))
        ):
            for action in actions:
                if action.hours_elapsed > repeat_every_hours:
                    logger.warning(
                        f"Action {action} hours_elapsed is greater than the repeat's repeat_every_hours. Skipping."
                    )
                    # don't allow schedualing events outside the repeat_every_hours, it's meaningless and confusing.
                    continue

                schedule.enter(
                    delay=hours_to_seconds(action.hours_elapsed),
                    priority=get_simple_priority(action),
                    action=wrapped_execute_action(
                        unit, experiment, job_name, logger, schedule, action, dry_run
                    ),
                )

            repeat_action.if_ = None  # not eval'd after the first loop
            repeat_action._completed_loops += 1

            if (max_hours is None) or (
                repeat_action._completed_loops * hours_to_seconds(repeat_every_hours)
                < hours_to_seconds(max_hours)
            ):
                schedule.enter(
                    delay=hours_to_seconds(repeat_every_hours),
                    priority=get_simple_priority(repeat_action),
                    action=wrapped_execute_action(
                        unit, experiment, job_name, logger, schedule, repeat_action, dry_run
                    ),
                )
            else:
                logger.debug(f"Exiting {repeat_action} loop as `max_hours` exceeded.")

        else:
            logger.debug(
                f"Action's `if` or `while` condition, `{if_=}` or `{while_=}`, evaluated False. Skipping."
            )

    return wrap_in_try_except(_callable, logger)


def log(
    unit: str,
    experiment: str,
    job_name: str,
    options: struct._LogOptions,
    dry_run: bool,
    if_: Optional[str | bool],
    logger: CustomLogger,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            return
        if (if_ is None) or evaluate_bool_expression(if_, unit):
            level = options.level.lower()
            getattr(logger, level)(options.message.format(unit=unit, job=job_name, experiment=experiment))
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def start_job(
    unit: str,
    experiment: str,
    job_name: str,
    options: dict,
    args: list,
    dry_run: bool,
    if_: Optional[str | bool],
    logger: CustomLogger,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            return

        if (if_ is None) or evaluate_bool_expression(if_, unit):
            if dry_run:
                logger.info(f"Dry-run: Starting {job_name} on {unit} with options {options} and args {args}.")
            else:
                publish(
                    f"pioreactor/{unit}/{experiment}/run/{job_name}",
                    encode(
                        {
                            "options": evaluate_options(options, unit) | {"job_source": "experiment_profile"},
                            "args": args,
                        }
                    ),
                )
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def pause_job(
    unit: str,
    experiment: str,
    job_name: str,
    dry_run: bool,
    if_: Optional[str | bool],
    logger: CustomLogger,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            return

        if (if_ is None) or evaluate_bool_expression(if_, unit):
            if dry_run:
                logger.info(f"Dry-run: Pausing {job_name} on {unit}.")
            else:
                publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "sleeping")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def resume_job(
    unit: str,
    experiment: str,
    job_name: str,
    dry_run: bool,
    if_: Optional[str | bool],
    logger: CustomLogger,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            return
        if (if_ is None) or evaluate_bool_expression(if_, unit):
            if dry_run:
                logger.info(f"Dry-run: Resuming {job_name} on {unit}.")
            else:
                publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "ready")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def stop_job(
    unit: str,
    experiment: str,
    job_name: str,
    dry_run: bool,
    if_: Optional[str | bool],
    logger: CustomLogger,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            return
        if (if_ is None) or evaluate_bool_expression(if_, unit):
            if dry_run:
                logger.info(f"Dry-run: Stopping {job_name} on {unit}.")
            else:
                publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "disconnected")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def update_job(
    unit: str,
    experiment: str,
    job_name: str,
    options: dict,
    dry_run: bool,
    if_: Optional[str | bool],
    logger: CustomLogger,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            return
        if (if_ is None) or evaluate_bool_expression(if_, unit):
            if dry_run:
                for setting, value in options.items():
                    logger.info(f"Dry-run: Updating {setting} to {value} in {job_name} on {unit}.")

            else:
                for setting, value in evaluate_options(options, unit).items():
                    publish(f"pioreactor/{unit}/{experiment}/{job_name}/{setting}/set", value)
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def hours_to_seconds(hours: float) -> float:
    return hours * 60 * 60


def _verify_experiment_profile(profile: struct.Profile) -> bool:
    # things to check for:
    # 1. Don't "stop" or "start" any *_automations
    # 2. Don't change generic settings on *_controllers, (Ex: changing target temp on temp_controller is wrong)
    # 3. check syntax of if statements

    actions_per_job = defaultdict(list)

    for unit in profile.pioreactors.values():
        for job in unit.jobs.keys():
            for action in unit.jobs[job].actions:
                actions_per_job[job].append(action)

    for job in profile.common.jobs.keys():
        for action in profile.common.jobs[job].actions:
            actions_per_job[job].append(action)

    # 1.
    def check_for_not_stopping_automations(action: struct.Action) -> bool:
        match action:
            case struct.Stop(_):
                raise ValueError(
                    f"Don't use 'stop' for automations. To stop automations, use 'stop' for controllers: {action}"
                )
            case struct.Start(_):
                raise ValueError(
                    f"Don't use 'start' for automations. To start automations, use 'start' for controllers with `options`: {action}"
                )
            case _:
                pass
        return True

    for automation_type in ["temperature_automation", "dosing_automation", "led_automation"]:
        assert all(check_for_not_stopping_automations(act) for act in actions_per_job[automation_type])

    # 2.
    def check_for_settings_change_on_controllers(action: struct.Action) -> bool:
        match action:
            case struct.Update(_, _, options):
                if "automation_name" not in options:
                    raise ValueError(f"Update automations, not controllers, with settings: {action}.")
        return True

    for control_type in ["temperature_control", "dosing_control", "led_control"]:
        assert all(check_for_settings_change_on_controllers(act) for act in actions_per_job[control_type])

    # 3.
    for job in actions_per_job:
        for action in actions_per_job[job]:
            if action.if_ and not check_syntax_of_bool_expression(action.if_):
                raise SyntaxError(f"Syntax error in {action}: `{action.if_}`")

            if (
                isinstance(action, struct.Repeat)
                and action.while_
                and not check_syntax_of_bool_expression(action.while_)
            ):
                raise SyntaxError(f"Syntax error in {action}: `{action.while_}`")

    return True


def _load_experiment_profile(profile_filename: str) -> struct.Profile:
    with open(profile_filename) as f:
        return decode(f.read(), type=struct.Profile)


def load_and_verify_profile(profile_filename: str) -> struct.Profile:
    profile = _load_experiment_profile(profile_filename)
    assert _verify_experiment_profile(profile), "profile is incorrect"
    return profile


def push_labels_to_ui(experiment, labels_map: dict[str, str]) -> None:
    try:
        for unit_name, label in labels_map.items():
            put(
                f"http://{leader_address}/api/experiments/{experiment}/unit_labels",
                encode({"unit": unit_name, "label": label}),
                headers={"Content-Type": "application/json"},
            )
    except Exception:
        pass


def get_installed_packages() -> dict[str, str]:
    import pkg_resources

    """Return a dictionary of installed packages and their versions"""
    installed_packages = {d.project_name: d.version for d in pkg_resources.working_set}
    return installed_packages


def check_plugins(plugins: list[struct.Plugin]) -> None:
    """Check if the specified packages with versions are installed"""

    if not plugins:
        # this can be slow, so skip it if no plugins are needed
        return

    installed_packages = get_installed_packages()
    not_installed = []

    for plugin in plugins:
        name = plugin.name
        version = plugin.version
        if name in installed_packages:
            if version.startswith(">="):
                # Version constraint is '>='
                if installed_packages[name] < version[2:]:
                    not_installed.append(plugin)
            if version.startswith("<="):
                # Version constraint is '<='
                if installed_packages[name] > version[2:]:
                    not_installed.append(plugin)
            else:
                # No version constraint, exact version match required
                if installed_packages[name] != version:
                    not_installed.append(plugin)
        else:
            not_installed.append(plugin)

    if not_installed:
        raise ImportError(f"Missing packages {not_installed}")


def execute_experiment_profile(profile_filename: str, experiment: str, dry_run: bool = False) -> None:
    unit = get_unit_name()
    action_name = "experiment_profile"
    logger = create_logger(action_name, unit=unit, experiment=experiment)
    with managed_lifecycle(unit, experiment, action_name, ignore_is_active_state=True) as state:
        try:
            profile = load_and_verify_profile(profile_filename)
        except Exception as e:
            logger.error(e)
            raise e

        state.mqtt_client.publish(
            f"pioreactor/{unit}/{experiment}/{action_name}/experiment_profile_name",
            profile.experiment_profile_name,
            retain=True,
        )

        if dry_run:
            logger.notice(  # type: ignore
                f"Executing DRY-RUN of profile {profile.experiment_profile_name}, sourced from {Path(profile_filename).name}. See logs."
            )
        else:
            logger.notice(  # type: ignore
                f"Executing profile {profile.experiment_profile_name}, sourced from {Path(profile_filename).name}."
            )

        try:
            check_plugins(profile.plugins)
        except Exception as e:
            logger.debug(e, exc_info=True)
            logger.error(e)
            raise e

        s = scheduler()

        # process common
        for job_name, job in profile.common.jobs.items():
            for action in job.actions:
                s.enter(
                    delay=hours_to_seconds(action.hours_elapsed),
                    priority=get_simple_priority(action),
                    action=common_wrapped_execute_action(
                        experiment,
                        job_name,
                        logger,
                        s,
                        action,
                        dry_run,
                    ),
                )

        # process specific pioreactors
        for unit_ in profile.pioreactors:
            pioreactor_specific_block = profile.pioreactors[unit_]
            if pioreactor_specific_block.label is not None:
                label = pioreactor_specific_block.label
                push_labels_to_ui(experiment, {unit_: label})

            for job_name, job in pioreactor_specific_block.jobs.items():
                for action in job.actions:
                    s.enter(
                        delay=hours_to_seconds(action.hours_elapsed),
                        priority=get_simple_priority(action),
                        action=wrapped_execute_action(
                            unit_,
                            experiment,
                            job_name,
                            logger,
                            s,
                            action,
                            dry_run,
                        ),
                    )

        logger.debug("Starting execution of actions.")

        try:
            # try / finally to handle keyboard interrupts

            # the below is so the schedule can be canceled by setting the event.
            while not state.exit_event.wait(timeout=0):
                next_event_in = s.run(blocking=False)
                if next_event_in is not None:
                    time.sleep(min(0.5, next_event_in))
                else:
                    break
        finally:
            if state.exit_event.is_set():
                # ended early

                # stop all jobs started
                # we can use active workers in experiment, since if a worker leaves an experiment or goes inactive, it's jobs are stopped
                workers = get_active_workers_in_experiment(experiment)
                with ClusterJobManager(workers) as jm:
                    jm.kill_jobs(experiment=experiment, job_source="experiment_profile")

                logger.notice(f"Stopping profile {profile.experiment_profile_name} early: {len(s.queue)} actions not started, and stopping all started actions.")  # type: ignore

            else:
                if dry_run:
                    logger.notice(  # type: ignore
                        f"Finished executing DRY-RUN of profile {profile.experiment_profile_name}."
                    )

                else:
                    logger.notice(f"Finished executing profile {profile.experiment_profile_name}.")  # type: ignore

            state.mqtt_client.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/experiment_profile_name",
                None,
                retain=True,
            )

            logger.clean_up()


@click.group(name="experiment_profile")
def click_experiment_profile():
    """
    (leader only) Run and manage experiment profiles
    """
    pass


@click_experiment_profile.command(name="execute")
@click.argument("filename", type=click.Path())
@click.argument("experiment", type=str)
@click.option("--dry-run", is_flag=True, help="Don't actually execute, just print to screen")
def click_execute_experiment_profile(filename: str, experiment, dry_run: bool) -> None:
    """
    (leader only) Run an experiment profile.
    """
    execute_experiment_profile(filename, experiment, dry_run)


@click_experiment_profile.command(name="verify")
@click.argument("filename", type=click.Path())
def click_verify_experiment_profile(filename: str) -> None:
    """
    (leader only) Verify an experiment profile for correctness.
    """
    load_and_verify_profile(filename)
