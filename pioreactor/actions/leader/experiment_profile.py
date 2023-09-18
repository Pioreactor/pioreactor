# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from threading import Timer
from typing import Callable

import click
import pkg_resources
from msgspec.json import encode
from msgspec.yaml import decode

from pioreactor.config import leader_address
from pioreactor.experiment_profiles import profile_struct as struct
from pioreactor.logging import create_logger
from pioreactor.mureq import put
from pioreactor.pubsub import publish
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_IDENTIFIER

ACTION_COUNT_LIMIT = 248


def execute_action(
    unit: str,
    experiment: str,
    job_name: str,
    logger,
    action: str,
    options=None,
    args=None,
    dry_run=False,
) -> Callable:
    # Handle each action type accordingly
    if action == "start":
        # start the job with the provided parameters
        return start_job(unit, experiment, job_name, options, args, dry_run, logger)
    elif action == "pause":
        # pause the job
        return pause_job(unit, experiment, job_name, dry_run, logger)
    elif action == "resume":
        # resume the job
        return resume_job(unit, experiment, job_name, dry_run, logger)
    elif action == "stop":
        # stop the job
        return stop_job(unit, experiment, job_name, dry_run, logger)
    elif action == "update":
        # update the job with the provided parameters
        return update_job(unit, experiment, job_name, options, dry_run, logger)
    else:
        raise ValueError(f"Not a valid action: {action}")


def start_job(
    unit: str, experiment: str, job_name: str, options: dict, args: list, dry_run: bool, logger
) -> Callable:
    if dry_run:
        return lambda: logger.info(
            f"Dry-run: Starting {job_name} on {unit} with options {options} and args {args}."
        )
    else:
        return lambda: publish(
            f"pioreactor/{unit}/{experiment}/run/{job_name}",
            encode({"options": options, "args": args}),
        )


def pause_job(unit: str, experiment: str, job_name: str, dry_run: bool, logger) -> Callable:
    if dry_run:
        return lambda: logger.info(f"Dry-run: Pausing {job_name} on {unit}.")
    else:
        return lambda: publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "sleeping")


def resume_job(unit: str, experiment: str, job_name: str, dry_run: bool, logger) -> Callable:
    if dry_run:
        return lambda: logger.info(f"Dry-run: Resuming {job_name} on {unit}.")
    else:
        return lambda: publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "ready")


def stop_job(unit: str, experiment: str, job_name: str, dry_run: bool, logger) -> Callable:
    if dry_run:
        return lambda: logger.info(f"Dry-run: Stopping {job_name} on {unit}.")
    else:
        return lambda: publish(
            f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "disconnected"
        )


def update_job(
    unit: str, experiment: str, job_name: str, options: dict, dry_run: bool, logger
) -> Callable:
    if dry_run:

        def _update():
            for setting, value in options.items():
                logger.info(f"Dry-run: Updating {setting} to {value} in {job_name} on {unit}.")

    else:

        def _update():
            for setting, value in options.items():
                publish(f"pioreactor/{unit}/{experiment}/{job_name}/{setting}/set", value)

    return _update


def hours_to_seconds(hours: float) -> float:
    return hours * 60 * 60


def load_and_verify_profile_file(profile_filename: str) -> struct.Profile:
    with open(profile_filename) as f:
        profile = decode(f.read(), type=struct.Profile)

    actions_per_job = defaultdict(list)

    for job in profile.common.keys():
        for action in profile.common[job]["actions"]:
            actions_per_job[job].append(action)

    for unit in profile.pioreactors.values():
        for job in unit["jobs"].keys():
            for action in unit["jobs"][job]["actions"]:
                actions_per_job[job].append(action)

    # TODO: things to check for:
    # 1. Don't "stop" any *_automations
    # 2. Don't change generic settings on *_controllers, (Ex: changing target temp on temp_controller is wrong)
    # 3. Current limitation with this architecture. We can't create more than 248 threads.

    # 1.
    def check_for_not_stopping_automations(act):
        if act.type == "stop":
            raise ValueError(
                "Don't use 'stop' for automations. To stop automations, use 'stop' for controllers."
            )
        return True

    for automation_type in ["temperature_automation", "dosing_automation", "led_automation"]:
        assert all(
            check_for_not_stopping_automations(act) for act in actions_per_job[automation_type]
        )

    # 2.
    def check_for_settings_change_on_controllers(act):
        if act.type == "update" and "automation-name" not in act.options:
            raise ValueError("Update automations, not controllers, with settings.")
        return True

    for control_type in ["temperature_control", "dosing_control", "led_control"]:
        assert all(
            check_for_settings_change_on_controllers(act) for act in actions_per_job[control_type]
        )

    # 3.
    assert (
        sum(len(x) for x in actions_per_job.values()) < ACTION_COUNT_LIMIT
    ), "Too many actions. Must be less than 248. Contact the Pioreactor authors."

    return profile


def publish_labels_to_ui(labels_map: dict[str, str]) -> None:
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
    """Return a dictionary of installed packages and their versions"""
    installed_packages = {d.project_name: d.version for d in pkg_resources.working_set}
    return installed_packages


def check_plugins(plugins: list[struct.Plugin]) -> None:
    """Check if the specified packages with versions are installed"""
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
            profile = load_and_verify_profile_file(profile_filename)
        except Exception as e:
            logger.error(e)
            raise e

        publish(
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

        labels_to_units = {v: k for k, v in profile.labels.items()}
        publish_labels_to_ui(profile.labels)

        timers = []

        # process common jobs
        for job in profile.common:
            for action in profile.common[job]["actions"]:
                t = Timer(
                    hours_to_seconds(action.hours_elapsed),
                    execute_action(
                        UNIVERSAL_IDENTIFIER,
                        experiment,
                        job,
                        logger,
                        action.type,
                        action.options,
                        action.args,
                        dry_run,
                    ),
                )
                t.daemon = True
                timers.append(t)

        # process specific jobs
        for unit_or_label in profile.pioreactors:
            _unit = labels_to_units.get(unit_or_label, unit_or_label)
            jobs = profile.pioreactors[unit_or_label]["jobs"]
            for job in jobs:
                for action in jobs[job]["actions"]:
                    t = Timer(
                        hours_to_seconds(action.hours_elapsed),
                        execute_action(
                            _unit,
                            experiment,
                            job,
                            logger,
                            action.type,
                            action.options,
                            action.args,
                            dry_run,
                        ),
                    )
                    t.daemon = True
                    timers.append(t)

        logger.debug(f"Starting execution of {len(timers)} actions.")
        for timer in timers:
            timer.start()

        try:
            while any((timer.is_alive() for timer in timers)) and not state.exit_event.wait(10):
                pass
        finally:
            publish(
                f"pioreactor/{unit}/{experiment}/{action_name}/experiment_profile_name",
                None,
                retain=True,
            )

            if state.exit_event.is_set():
                # ended early
                for timer in timers:
                    timer.cancel()
                logger.notice(f"Exiting profile {profile.experiment_profile_name} early.")  # type: ignore
            else:
                if dry_run:
                    logger.notice(  # type: ignore
                        f"Finished executing DRY-RUN of profile {profile.experiment_profile_name}."
                    )

                else:
                    logger.notice(f"Finished executing profile {profile.experiment_profile_name}.")  # type: ignore


@click.group(name="experiment_profile")
def click_experiment_profile():
    pass


@click_experiment_profile.command(name="execute")
@click.argument("filename", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Don't actually execute, just print to screen")
def click_execute_experiment_profile(filename: str, dry_run: bool) -> None:
    """
    (leader only) Run an experiment profile.
    """
    execute_experiment_profile(filename, dry_run)


@click_experiment_profile.command(name="verify")
@click.argument("filename", type=click.Path(exists=True))
def click_verify_experiment_profile(filename: str) -> None:
    """
    (leader only) Verify an experiment profile for correctness.
    """
    load_and_verify_profile_file(filename)
