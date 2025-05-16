# -*- coding: utf-8 -*-
from __future__ import annotations

import random
import time
from collections import defaultdict
from pathlib import Path
from sched import scheduler
from time import perf_counter
from typing import Any
from typing import Callable

import click
from msgspec.yaml import decode

from pioreactor.cluster_management import get_active_workers_in_experiment
from pioreactor.exc import MQTTValueError
from pioreactor.exc import NotAssignedAnExperimentError
from pioreactor.experiment_profiles import profile_struct as struct
from pioreactor.logging import create_logger
from pioreactor.logging import CustomLogger
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import get_from
from pioreactor.pubsub import patch_into
from pioreactor.pubsub import patch_into_leader
from pioreactor.pubsub import post_into_leader
from pioreactor.utils import ClusterJobManager
from pioreactor.utils import long_running_managed_lifecycle
from pioreactor.utils.networking import resolve_to_address
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env

BoolExpression = str | bool
Env = dict[str, Any]

STRICT_EXPRESSION_PATTERN = r"^\${{(.*?)}}$"
FLEXIBLE_EXPRESSION_PATTERN = r"\${{(.*?)}}"


class ActionMetrics:
    def __init__(self):
        self.count = 0
        self._start = perf_counter()

    def hours_elapsed(self) -> float:
        return seconds_to_hours(perf_counter() - self._start)

    def increment(self) -> int:
        self.count += 1
        return self.count


def wrap_in_try_except(func, logger: CustomLogger) -> Callable:
    def inner_function(*args, **kwargs) -> None:
        try:
            func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Error in action: {e}")

    return inner_function


def is_bracketed_expression(value: str) -> bool:
    import re

    return bool(re.search(STRICT_EXPRESSION_PATTERN, str(value)))


def strip_expression_brackets(value: str) -> str:
    import re

    match = re.search(STRICT_EXPRESSION_PATTERN, value)
    assert match is not None
    return match.group(1)


def evaluate_options(options: dict, env: dict) -> dict:
    """
    Users can provide options like {'target_rpm': '${{ bioreactor_A:stirring:target_rpm + 10 }}'}, and the latter
    should be evaluated
    """
    from pioreactor.experiment_profiles.parser import parse_profile_expression

    options_expressed = {}
    for key, value in options.items():
        if is_bracketed_expression(value):
            expression = strip_expression_brackets(value)
            options_expressed[key] = parse_profile_expression(expression, env=env)
        else:
            options_expressed[key] = value
    return options_expressed


def evaluate_log_message(message: str, env: dict) -> str:
    import re
    from pioreactor.experiment_profiles.parser import parse_profile_expression

    matches = re.findall(FLEXIBLE_EXPRESSION_PATTERN, message)

    modified_matches = [parse_profile_expression(match, env) for match in matches]

    # Replace each ${{...}} in the original string with the modified match
    result_string = re.sub(FLEXIBLE_EXPRESSION_PATTERN, lambda m: str(modified_matches.pop(0)), message)
    return result_string


def evaluate_bool_expression(bool_expression: BoolExpression, env: dict) -> bool:
    from pioreactor.experiment_profiles.parser import parse_profile_expression_to_bool

    if isinstance(bool_expression, bool):
        return bool_expression

    if is_bracketed_expression(bool_expression):
        bool_expression = strip_expression_brackets(bool_expression)

    # bool_expression is a str
    return parse_profile_expression_to_bool(bool_expression, env=env)


def check_syntax_of_bool_expression(bool_expression: BoolExpression) -> bool:
    from pioreactor.experiment_profiles.parser import check_syntax

    if isinstance(bool_expression, bool):
        return True

    if is_bracketed_expression(bool_expression):
        bool_expression = strip_expression_brackets(bool_expression)

    # TODO: in a common expressions, users can use ::word:work which is technically not valid syntax. For checking, we replace with garbage
    bool_expression = bool_expression.replace("::", "dummy:", 1)

    return check_syntax(bool_expression)


def check_if_job_running(unit: str, job: str) -> bool:
    if is_testing_env():
        return True
    try:
        r = get_from(resolve_to_address(unit), f"/unit_api/jobs/running/{job}")
        r.raise_for_status()
        return len(r.json()) > 0
    except HTTPException:
        # an http hiccup shouldn't stall commands
        return True


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
        case struct.When():
            return 5
        case struct.Repeat():
            return 6
        case struct.Log():
            return 10
        case _:
            raise ValueError(f"Not a defined action: {action}")


def wrapped_execute_action(
    unit: str,
    experiment: str,
    global_env: Env,
    job_name: str,
    logger: CustomLogger,
    schedule: scheduler,
    action_metrics: ActionMetrics,
    parent_job: long_running_managed_lifecycle,
    action: struct.Action,
    dry_run: bool = False,
) -> Callable[..., None]:
    # hack...
    if job_name == "led_intensity":
        action = _led_intensity_hack(action)

    env = global_env | {"unit": unit, "experiment": experiment, "job_name": job_name}

    match action:
        case struct.Start(_, if_, options, args):
            return start_job(
                unit,
                experiment,
                parent_job,
                job_name,
                dry_run,
                if_,
                env,
                logger,
                action_metrics,
                options,
                args,
            )

        case struct.Pause(_, if_):
            return pause_job(
                unit, experiment, parent_job, job_name, dry_run, if_, env, logger, action_metrics
            )

        case struct.Resume(_, if_):
            return resume_job(
                unit, experiment, parent_job, job_name, dry_run, if_, env, logger, action_metrics
            )

        case struct.Stop(_, if_):
            return stop_job(unit, experiment, parent_job, job_name, dry_run, if_, env, logger, action_metrics)

        case struct.Update(_, if_, options):
            return update_job(
                unit,
                experiment,
                parent_job,
                job_name,
                dry_run,
                if_,
                env,
                logger,
                action_metrics,
                options,
            )

        case struct.Log(_, options, if_):
            return log(
                unit,
                experiment,
                parent_job,
                job_name,
                dry_run,
                if_,
                env,
                logger,
                action_metrics,
                options,
            )

        case struct.Repeat(_, if_, repeat_every_hours, while_, max_hours, actions):
            return repeat(
                unit,
                experiment,
                parent_job,
                job_name,
                dry_run,
                if_,
                env,
                logger,
                action_metrics,
                action,
                while_,
                repeat_every_hours,
                max_hours,
                actions,
                schedule,
            )

        case struct.When(_, if_, condition, actions):
            return when(
                unit,
                experiment,
                parent_job,
                job_name,
                dry_run,
                if_,
                env,
                logger,
                action_metrics,
                condition,
                action,
                actions,
                schedule,
            )

        case _:
            raise ValueError(f"Not a valid action: {action}")


def chain_functions(*funcs: Callable[[], None]) -> Callable[[], None]:
    def combined_function() -> None:
        for func in funcs:
            time.sleep(0.01)  # add a tiny sleep to avoid overloading webservers
            func()

    return combined_function


def common_wrapped_execute_action(
    experiment: str,
    job_name: str,
    global_env: Env,
    logger: CustomLogger,
    schedule: scheduler,
    action_metrics: ActionMetrics,
    parent_job: long_running_managed_lifecycle,
    action: struct.Action,
    dry_run: bool = False,
) -> Callable[..., None]:
    actions_to_execute = []
    for worker in get_active_workers_in_experiment(experiment):
        actions_to_execute.append(
            wrapped_execute_action(
                worker,
                experiment,
                global_env,
                job_name,
                logger,
                schedule,
                action_metrics,
                parent_job,
                action,
                dry_run,
            )
        )

    return chain_functions(*actions_to_execute)


def when(
    unit: str,
    experiment: str,
    parent_job: long_running_managed_lifecycle,
    job_name: str,
    dry_run: bool,
    if_: BoolExpression | None,
    env: dict,
    logger: CustomLogger,
    action_metrics: ActionMetrics,
    condition: BoolExpression,
    when_action: struct.When,
    actions: list[struct.Action],
    schedule: scheduler,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if (get_assigned_experiment_name(unit) != experiment) and not is_testing_env():
            return

        nonlocal env
        env = env | {"hours_elapsed": action_metrics.hours_elapsed(), "action_count": action_metrics.count}

        if (if_ is None) or evaluate_bool_expression(if_, env):
            try:
                condition_met = evaluate_bool_expression(condition, env)
            except MQTTValueError:
                condition_met = False
                # log randomly.
                if random.random() < 1 / 45.0:  # on average, once every 15min.
                    logger.warning(
                        f"Data not found in MQTT for condition `{condition}`. Double check the fields and that the required jobs are running"
                    )

            if condition_met:
                for action in actions:
                    schedule.enter(
                        delay=hours_to_seconds(action.hours_elapsed),
                        priority=get_simple_priority(action),
                        action=wrapped_execute_action(
                            unit,
                            experiment,
                            env,
                            job_name,
                            logger,
                            schedule,
                            action_metrics,
                            parent_job,
                            action,
                            dry_run,
                        ),
                    )

            else:
                schedule.enter(
                    # adding a random element eventually smooth out these checks, so that there's not a thundering herd to check, and allows other actions to execute inbetween.
                    delay=15 + 10 * random.random(),
                    priority=get_simple_priority(when_action),
                    action=wrapped_execute_action(
                        unit,
                        experiment,
                        env,
                        job_name,
                        logger,
                        schedule,
                        action_metrics,
                        parent_job,
                        when_action,
                        dry_run,
                    ),
                )

        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def repeat(
    unit: str,
    experiment: str,
    parent_job: long_running_managed_lifecycle,
    job_name: str,
    dry_run: bool,
    if_: BoolExpression | None,
    env: dict,
    logger: CustomLogger,
    action_metrics: ActionMetrics,
    repeat_action: struct.Repeat,
    while_: BoolExpression | None,
    repeat_every_hours: float,
    max_hours: float | None,
    actions: list[struct.BasicAction],
    schedule: scheduler,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            logger.debug(
                f"Skipping repeat action on {unit} do to not being assigned to experiment {experiment}."
            )
            return

        nonlocal env
        env = env | {"hours_elapsed": action_metrics.hours_elapsed(), "action_count": action_metrics.count}

        if ((if_ is None) or evaluate_bool_expression(if_, env)) and (
            ((while_ is None) or evaluate_bool_expression(while_, env))
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
                        unit,
                        experiment,
                        env,
                        job_name,
                        logger,
                        schedule,
                        action_metrics,
                        parent_job,
                        action,
                        dry_run,
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
                        unit,
                        experiment,
                        env,
                        job_name,
                        logger,
                        schedule,
                        action_metrics,
                        parent_job,
                        repeat_action,
                        dry_run,
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
    parent_job: long_running_managed_lifecycle,
    job_name: str,
    dry_run: bool,
    if_: BoolExpression | None,
    env: dict,
    logger: CustomLogger,
    action_metrics: ActionMetrics,
    options: struct._LogOptions,
) -> Callable[..., None]:
    def _callable() -> None:
        # first check if the Pioreactor is still part of the experiment.

        if get_assigned_experiment_name(unit) != experiment:
            logger.debug(
                f"Skipping log action on {unit} do to not being assigned to experiment {experiment}."
            )

            return

        nonlocal env
        env = env | {"hours_elapsed": action_metrics.hours_elapsed(), "action_count": action_metrics.count}

        if (if_ is None) or evaluate_bool_expression(if_, env):
            body = {
                "message": evaluate_log_message(options.message, env),
                "timestamp": current_utc_timestamp(),
                "level": options.level,
                "source": parent_job.job_key,
                "task": parent_job.job_key,
                "_souce": "app",
            }
            post_into_leader(
                f"/api/workers/{unit}/experiments/{experiment}/logs", json=body
            ).raise_for_status()
            # getattr(logger, level)(evaluate_log_message(options.message, env))
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def start_job(
    unit: str,
    experiment: str,
    parent_job: long_running_managed_lifecycle,
    job_name: str,
    dry_run: bool,
    if_: BoolExpression | None,
    env: dict,
    logger: CustomLogger,
    action_metrics: ActionMetrics,
    options: dict,
    args: list,
) -> Callable[..., None]:
    def _callable() -> None:
        action_count = action_metrics.increment()
        parent_job.publish_setting("action_count", action_count)

        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            logger.debug(
                f"Skipping start action on {unit} do to not being assigned to experiment {experiment}."
            )
            return

        nonlocal env
        env = env | {"hours_elapsed": action_metrics.hours_elapsed(), "action_count": action_metrics.count}

        if (if_ is None) or evaluate_bool_expression(if_, env):
            if dry_run:
                logger.info(
                    f"{action_count}. Dry-run: Starting {job_name} on {unit} with options {options} and args {args}."
                )
            else:
                logger.debug(
                    f"{action_count}. Starting {job_name} on {unit} with options {options} and args {args}."
                )
                patch_into(
                    resolve_to_address(unit),
                    f"/unit_api/jobs/run/job_name/{job_name}",
                    json={
                        "options": evaluate_options(options, env),
                        "env": {
                            "JOB_SOURCE": parent_job.job_key,
                            "EXPERIMENT": experiment,
                        },
                        "args": args,
                    },
                ).raise_for_status()
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def pause_job(
    unit: str,
    experiment: str,
    parent_job: long_running_managed_lifecycle,
    job_name: str,
    dry_run: bool,
    if_: BoolExpression | None,
    env: dict,
    logger: CustomLogger,
    action_metrics: ActionMetrics,
) -> Callable[..., None]:
    def _callable() -> None:
        action_count = action_metrics.increment()
        parent_job.publish_setting("action_count", action_count)

        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            logger.debug(
                f"Skipping pause action on {unit} do to not being assigned to experiment {experiment}."
            )
            return

        nonlocal env
        env = env | {"hours_elapsed": action_metrics.hours_elapsed(), "action_count": action_metrics.count}

        if (if_ is None) or evaluate_bool_expression(if_, env):
            if dry_run:
                logger.info(f"{action_count}. Dry-run: Pausing {job_name} on {unit}.")
            else:
                logger.debug(f"{action_count}. Pausing {job_name} on {unit}.")
                if check_if_job_running(unit, job_name):
                    patch_into_leader(
                        f"/api/workers/{unit}/jobs/update/job_name/{job_name}/experiments/{experiment}",
                        json={"settings": {"$state": "sleeping"}},
                    ).raise_for_status()
                else:
                    logger.debug(f"Job {job_name} not running on {unit}.")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def resume_job(
    unit: str,
    experiment: str,
    parent_job: long_running_managed_lifecycle,
    job_name: str,
    dry_run: bool,
    if_: BoolExpression | None,
    env: dict,
    logger: CustomLogger,
    action_metrics: ActionMetrics,
) -> Callable[..., None]:
    def _callable() -> None:
        action_count = action_metrics.increment()
        parent_job.publish_setting("action_count", action_count)

        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            logger.debug(
                f"Skipping resume action on {unit} do to not being assigned to experiment {experiment}."
            )

            return

        nonlocal env
        env = env | {"hours_elapsed": action_metrics.hours_elapsed(), "action_count": action_metrics.count}

        if (if_ is None) or evaluate_bool_expression(if_, env):
            if dry_run:
                logger.info(f"{action_count}. Dry-run: Resuming {job_name} on {unit}.")
            else:
                logger.debug(f"{action_count}. Resuming {job_name} on {unit}.")
                if check_if_job_running(unit, job_name):
                    patch_into_leader(
                        f"/api/workers/{unit}/jobs/update/job_name/{job_name}/experiments/{experiment}",
                        json={"settings": {"$state": "ready"}},
                    ).raise_for_status()
                else:
                    logger.debug(f"Job {job_name} not running on {unit}.")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def stop_job(
    unit: str,
    experiment: str,
    parent_job: long_running_managed_lifecycle,
    job_name: str,
    dry_run: bool,
    if_: BoolExpression | None,
    env: dict,
    logger: CustomLogger,
    action_metrics: ActionMetrics,
) -> Callable[..., None]:
    def _callable() -> None:
        action_count = action_metrics.increment()
        parent_job.publish_setting("action_count", action_count)

        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            logger.debug(
                f"Skipping stop action on {unit} do to not being assigned to experiment {experiment}."
            )

            return

        nonlocal env
        env = env | {"hours_elapsed": action_metrics.hours_elapsed(), "action_count": action_metrics.count}

        if (if_ is None) or evaluate_bool_expression(if_, env):
            if dry_run:
                logger.info(f"{action_count}. Dry-run: Stopping {job_name} on {unit}.")
            else:
                logger.debug(f"{action_count}. Stopping {job_name} on {unit}.")
                patch_into_leader(
                    f"/api/workers/{unit}/jobs/stop/job_name/{job_name}/experiments/{experiment}",
                ).raise_for_status()
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def update_job(
    unit: str,
    experiment: str,
    parent_job: long_running_managed_lifecycle,
    job_name: str,
    dry_run: bool,
    if_: BoolExpression | None,
    env: dict,
    logger: CustomLogger,
    action_metrics: ActionMetrics,
    options: dict,
) -> Callable[..., None]:
    def _callable() -> None:
        action_count = action_metrics.increment()
        parent_job.publish_setting("action_count", action_count)

        # first check if the Pioreactor is still part of the experiment.
        if get_assigned_experiment_name(unit) != experiment:
            logger.debug(
                f"Skipping update action on {unit} do to not being assigned to experiment {experiment}."
            )

            return

        nonlocal env
        env = env | {"hours_elapsed": action_metrics.hours_elapsed(), "action_count": action_metrics.count}

        if (if_ is None) or evaluate_bool_expression(if_, env):
            if dry_run:
                for setting, value in options.items():
                    logger.info(
                        f"{action_count}. Dry-run: Updating {setting} to {value} in {job_name} on {unit}."
                    )

            else:
                for setting, value in evaluate_options(options, env).items():
                    logger.debug(f"{action_count}. Updating {setting} to {value} in {job_name} on {unit}.")
                    if check_if_job_running(unit, job_name):
                        patch_into_leader(
                            f"/api/workers/{unit}/jobs/update/job_name/{job_name}/experiments/{experiment}",
                            json={"settings": {setting: value}},
                        ).raise_for_status()
                    else:
                        logger.debug(f"Job {job_name} not running on {unit}.")
        else:
            logger.debug(f"Action's `if` condition, `{if_}`, evaluated False. Skipping action.")

    return wrap_in_try_except(_callable, logger)


def hours_to_seconds(hours: float) -> float:
    return hours * 60 * 60


def seconds_to_hours(seconds: float) -> float:
    return seconds / 60.0 / 60.0


def _verify_experiment_profile(profile: struct.Profile) -> bool:
    # things to check for:
    # 1. check syntax of if statements

    actions_per_job = defaultdict(list)

    for unit in profile.pioreactors.values():
        for job in unit.jobs.keys():
            for action in unit.jobs[job].actions:
                actions_per_job[job].append(action)

    for job in profile.common.jobs.keys():
        for action in profile.common.jobs[job].actions:
            actions_per_job[job].append(action)

    # 1.
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
            patch_into_leader(
                f"/api/experiments/{experiment}/unit_labels", json={"unit": unit_name, "label": label}
            ).raise_for_status()
    except Exception:
        pass


def get_installed_plugins_and_versions() -> dict[str, str]:
    from pioreactor.plugin_management import get_plugins

    local_plugins = {name: metadata.version for name, metadata in get_plugins().items()}
    return local_plugins


def check_plugins(required_plugins: list[struct.Plugin]) -> None:
    """Check if the specified plugins with versions are installed"""

    if not required_plugins:
        # this can be slow, so skip it if no plugins are needed
        return

    from packaging.version import Version

    installed_plugins = get_installed_plugins_and_versions()
    not_installed = []

    for required_plugin in required_plugins:
        required_name = required_plugin.name
        required_version = required_plugin.version
        if required_name in installed_plugins:
            installed_version = Version(installed_plugins[required_name])
            if required_version.startswith(">="):
                # Version constraint is '>='
                if not (installed_version >= Version(required_version[2:])):
                    not_installed.append(required_plugin)
            elif required_version.startswith("<="):
                # Version constraint is '<='
                if not (installed_version <= Version(required_version[2:])):
                    not_installed.append(required_plugin)
            elif required_version.startswith("=="):
                # specific version constraint, exact version match required
                if installed_version != Version(required_version):
                    not_installed.append(required_plugin)
            else:
                # No version constraint, exact version match required
                if installed_version != Version(required_version):
                    not_installed.append(required_plugin)
        else:
            not_installed.append(required_plugin)

    if not_installed:
        raise ImportError(f"Missing plugins: {not_installed}")


def execute_experiment_profile(profile_filename: str, experiment: str, dry_run: bool = False) -> None:
    unit = get_unit_name()
    action_name = "experiment_profile"
    with long_running_managed_lifecycle(unit, experiment, action_name) as mananged_job:
        logger = create_logger(mananged_job.job_key, unit=unit, experiment=experiment)

        try:
            profile = load_and_verify_profile(profile_filename)
        except Exception as e:
            logger.error(e)
            raise e

        mananged_job.publish_setting(
            "experiment_profile_name",
            profile.experiment_profile_name,
        )
        mananged_job.publish_setting(
            "start_time_utc",
            current_utc_timestamp(),
        )
        mananged_job.publish_setting(
            "profile_filename",
            Path(profile_filename).name,
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

        global_env = profile.inputs

        sched = scheduler()

        action_metrics = ActionMetrics()

        for job_name, job in profile.common.jobs.items():
            for action in job.actions:
                sched.enter(
                    delay=hours_to_seconds(action.hours_elapsed),
                    priority=get_simple_priority(action),
                    action=common_wrapped_execute_action(
                        experiment,
                        job_name,
                        global_env,
                        logger,
                        sched,
                        action_metrics,
                        mananged_job,
                        action,
                        dry_run,
                    ),
                )

        # process specific pioreactors
        for unit_ in profile.pioreactors:
            try:
                assigned_experiment = get_assigned_experiment_name(unit_)
            except NotAssignedAnExperimentError:
                assigned_experiment = None

            if (assigned_experiment != experiment) and not is_testing_env():
                logger.warning(
                    f"There exists profile actions for {unit_}, but it's not assigned to experiment {experiment}. Skipping scheduling actions."
                )
                continue

            pioreactor_specific_block = profile.pioreactors[unit_]
            if pioreactor_specific_block.label is not None:
                label = pioreactor_specific_block.label
                push_labels_to_ui(experiment, {unit_: label})

            for job_name, job in pioreactor_specific_block.jobs.items():
                for action in job.actions:
                    sched.enter(
                        delay=hours_to_seconds(action.hours_elapsed),
                        priority=get_simple_priority(action),
                        action=wrapped_execute_action(
                            unit_,
                            experiment,
                            global_env,
                            job_name,
                            logger,
                            sched,
                            action_metrics,
                            mananged_job,
                            action,
                            dry_run,
                        ),
                    )

        logger.debug("Starting execution of actions.")

        try:
            # try / finally to handle keyboard interrupts

            # the below is so the schedule can be canceled by setting the event.
            while not mananged_job.exit_event.wait(timeout=0):
                next_event_in = sched.run(blocking=False)
                if next_event_in is not None:
                    time.sleep(min(0.25, next_event_in))
                else:
                    break
        finally:
            if mananged_job.exit_event.is_set():
                # ended early

                logger.notice(f"Stopping profile `{profile.experiment_profile_name}` early: {action_metrics.count} actions(s) completed, {len(sched.queue)} action(s) not started. Stopping all started jobs.")  # type: ignore
                # stop all jobs started
                # we can use active workers in experiment, since if a worker leaves an experiment or goes inactive, it's jobs are stopped
                workers = get_active_workers_in_experiment(experiment)
                with ClusterJobManager() as cjm:
                    cjm.kill_jobs(workers, experiment=experiment, job_source=mananged_job.job_key)

            else:
                time.sleep(
                    0.5
                )  # wait N second for last commands to finish being sent and processed, else the user sees out of order events.
                if dry_run:
                    logger.info(f"Finished executing DRY-RUN of profile {profile.experiment_profile_name}.")

                else:
                    logger.info(f"Finished executing profile {profile.experiment_profile_name}.")

            mananged_job.publish_setting("experiment_profile_name", None)
            mananged_job.publish_setting("start_time_utc", None)

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
def click_execute_experiment_profile(filename: str, experiment: str, dry_run: bool) -> None:
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
