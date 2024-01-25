# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path
from sched import scheduler
from typing import Callable
from typing import Optional

import click
from msgspec.json import encode
from msgspec.yaml import decode

from pioreactor.config import leader_address
from pioreactor.experiment_profiles import profile_struct as struct
from pioreactor.experiment_profiles.parser import check_syntax
from pioreactor.experiment_profiles.parser import parse_profile_expression
from pioreactor.experiment_profiles.parser import parse_profile_expression_to_bool
from pioreactor.logging import create_logger
from pioreactor.mureq import put
from pioreactor.pubsub import publish
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_IDENTIFIER


def wrap_in_try_except(func, logger):
    def inner_function(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Error in action: {e}")

    return inner_function


def is_bracketed_expression(value) -> bool:
    pattern = r"\${{(.*?)}}"
    return bool(re.search(pattern, str(value)))


def strip_expression_brackets(value) -> str:
    pattern = r"\${{(.*?)}}"
    match = re.search(pattern, value)
    assert match is not None
    return match.group(1)


def evaluate_options(options: dict) -> dict:
    """
    Users can provide options like {'target_rpm': '${{ bioreactor_A:stirring:target_rpm + 10 }}'}, and the latter
    should be evaluated
    """
    for key, value in options.items():
        if is_bracketed_expression(value):
            options[key] = parse_profile_expression(strip_expression_brackets(value))
    return options


def evaluate_if(if_expression: str | bool) -> bool:
    if isinstance(if_expression, bool):
        return if_expression

    if is_bracketed_expression(if_expression):
        if_expression = strip_expression_brackets(if_expression)
    return parse_profile_expression_to_bool(if_expression)


def check_syntax_of_if_expression(if_expression: str | bool) -> bool:
    if isinstance(if_expression, bool):
        return True

    if is_bracketed_expression(if_expression):
        if_expression = strip_expression_brackets(if_expression)
    return check_syntax(if_expression)


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

        case struct.Pause(hours, if_) | struct.Stop(hours, if_):
            options = {"A": 0, "B": 0, "C": 0, "D": 0}
            return struct.Start(hours, if_, options, [])

        case struct.Update(hours, if_, options):
            return struct.Start(hours, if_, options, [])

        case _:
            raise ValueError


def get_simple_priority(action):
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
        case struct.Log():
            return 10
        case _:
            raise ValueError(f"Not a valid action: {action}")


def wrapped_execute_action(
    unit: str,
    experiment: str,
    job_name: str,
    logger,
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

        case _:
            raise ValueError(f"Not a valid action: {action}")


def log(
    unit: str,
    experiment: str,
    job_name: str,
    options: struct._LogOptions,
    dry_run: bool,
    if_: Optional[str | bool],
    logger,
) -> Callable[..., None]:
    def _callable() -> None:
        if (if_ is None) or evaluate_if(if_):
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
    logger,
) -> Callable[..., None]:
    def _callable() -> None:
        if (if_ is None) or evaluate_if(if_):
            if dry_run:
                logger.info(f"Dry-run: Starting {job_name} on {unit} with options {options} and args {args}.")
            else:
                publish(
                    f"pioreactor/{unit}/{experiment}/run/{job_name}",
                    encode({"options": evaluate_options(options), "args": args}),
                )
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def pause_job(
    unit: str, experiment: str, job_name: str, dry_run: bool, if_: Optional[str | bool], logger
) -> Callable[..., None]:
    def _callable() -> None:
        if (if_ is None) or evaluate_if(if_):
            if dry_run:
                logger.info(f"Dry-run: Pausing {job_name} on {unit}.")
            else:
                publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "sleeping")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def resume_job(
    unit: str, experiment: str, job_name: str, dry_run: bool, if_: Optional[str | bool], logger
) -> Callable[..., None]:
    def _callable() -> None:
        if (if_ is None) or evaluate_if(if_):
            if dry_run:
                logger.info(f"Dry-run: Resuming {job_name} on {unit}.")
            else:
                publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "ready")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def stop_job(
    unit: str, experiment: str, job_name: str, dry_run: bool, if_: Optional[str | bool], logger
) -> Callable[..., None]:
    def _callable() -> None:
        if (if_ is None) or evaluate_if(if_):
            if dry_run:
                logger.info(f"Dry-run: Stopping {job_name} on {unit}.")
            else:
                publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "disconnected")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def update_job(
    unit: str, experiment: str, job_name: str, options: dict, dry_run: bool, if_: Optional[str | bool], logger
) -> Callable[..., None]:
    def _callable() -> None:
        if (if_ is None) or evaluate_if(if_):
            if dry_run:
                for setting, value in options.items():
                    logger.info(f"Dry-run: Updating {setting} to {value} in {job_name} on {unit}.")

            else:
                for setting, value in evaluate_options(options).items():
                    publish(f"pioreactor/{unit}/{experiment}/{job_name}/{setting}/set", value)
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def hours_to_seconds(hours: float) -> float:
    return hours * 60 * 60


def _verify_experiment_profile(profile: struct.Profile) -> struct.Profile:
    # things to check for:
    # 1. Don't "stop" or "start" any *_automations
    # 2. Don't change generic settings on *_controllers, (Ex: changing target temp on temp_controller is wrong)
    # 3. check syntax of if statements
    # 4. No if statements in the common

    actions_per_job = defaultdict(list)

    for job in profile.common.jobs.keys():
        for action in profile.common.jobs[job].actions:
            actions_per_job[job].append(action)
            # 4.
            if action.if_ is not None:
                raise ValueError("Can't put `if` in common yet!")

    for unit in profile.pioreactors.values():
        for job in unit.jobs.keys():
            for action in unit.jobs[job].actions:
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
            if action.if_ and not check_syntax_of_if_expression(action.if_):
                raise SyntaxError(f"Syntax error in `{action.if_}`")

    return profile


def _load_experiment_profile(profile_filename: str) -> struct.Profile:
    with open(profile_filename) as f:
        return decode(f.read(), type=struct.Profile)


def load_and_verify_profile(profile_filename: str) -> struct.Profile:
    profile = _load_experiment_profile(profile_filename)
    _verify_experiment_profile(profile)
    return profile


def push_labels_to_ui(labels_map: dict[str, str]) -> None:
    try:
        for unit_name, label in labels_map.items():
            put(
                f"http://{leader_address}/api/unit_labels/current",
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


def execute_experiment_profile(profile_filename: str, dry_run: bool = False) -> None:
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    action_name = "experiment_profile"
    logger = create_logger(action_name)
    with publish_ready_to_disconnected_state(unit, experiment, action_name) as state:
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
                    action=wrapped_execute_action(
                        UNIVERSAL_IDENTIFIER,
                        experiment,
                        job_name,
                        logger,
                        action,
                        dry_run,
                    ),
                )

        # process specific pioreactors
        for unit_ in profile.pioreactors:
            pioreactor_specific_block = profile.pioreactors[unit_]
            if pioreactor_specific_block.label is not None:
                label = pioreactor_specific_block.label
                push_labels_to_ui({unit_: label})

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
                            action,
                            dry_run,
                        ),
                    )

        logger.debug(f"Starting execution of {len(s.queue)} actions.")

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
            state.mqtt_client.publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/experiment_profile_name",
                None,
                retain=True,
            )

            if state.exit_event.is_set():
                # ended early
                logger.notice(f"Exiting profile {profile.experiment_profile_name} early: {len(s.queue)} actions not started.")  # type: ignore
            else:
                if dry_run:
                    logger.notice(  # type: ignore
                        f"Finished executing DRY-RUN of profile {profile.experiment_profile_name}."
                    )

                else:
                    logger.notice(f"Finished executing profile {profile.experiment_profile_name}.")  # type: ignore


@click.group(name="experiment_profile")
def click_experiment_profile():
    """
    (leader only) Run and manage experiment profiles
    """
    pass


@click_experiment_profile.command(name="execute")
@click.argument("filename", type=click.Path())
@click.option("--dry-run", is_flag=True, help="Don't actually execute, just print to screen")
def click_execute_experiment_profile(filename: str, dry_run: bool) -> None:
    """
    (leader only) Run an experiment profile.
    """
    execute_experiment_profile(filename, dry_run)


@click_experiment_profile.command(name="verify")
@click.argument("filename", type=click.Path())
def click_verify_experiment_profile(filename: str) -> None:
    """
    (leader only) Verify an experiment profile for correctness.
    """
    load_and_verify_profile(filename)
