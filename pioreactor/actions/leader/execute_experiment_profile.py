# -*- coding: utf-8 -*-
from __future__ import annotations

from threading import Timer
from typing import Callable

import click
from msgspec.json import encode
from msgspec.yaml import decode

from pioreactor.config import leader_address
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.logging import create_logger
from pioreactor.mureq import put
from pioreactor.pubsub import publish
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_IDENTIFIER


def execute_action(
    unit: str, experiment: str, job_name: str, action: str, options=None, args=None
) -> Callable:
    # Handle each action type accordingly
    if action == "start":
        # start the job with the provided parameters
        return start_job(unit, experiment, job_name, options, args)
    elif action == "pause":
        # pause the job
        return pause_job(unit, experiment, job_name)
    elif action == "resume":
        # resume the job
        return resume_job(unit, experiment, job_name)
    elif action == "stop":
        # stop the job
        return stop_job(unit, experiment, job_name)
    elif action == "update":
        # update the job with the provided parameters
        return update_job(unit, experiment, job_name, options)
    else:
        raise ValueError(f"Not a valid action: {action}")


def start_job(unit, experiment, job_name, options, args):
    return lambda: publish(
        f"pioreactor/{unit}/{experiment}/run/{job_name}",
        encode({"options": options, "args": args}),
    )


def pause_job(unit, experiment, job_name):
    return lambda: publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "sleeping")


def resume_job(unit, experiment, job_name):
    return lambda: publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "ready")


def stop_job(unit, experiment, job_name):
    return lambda: publish(f"pioreactor/{unit}/{experiment}/{job_name}/$state/set", "disconnected")


def update_job(unit, experiment, job_name, options):
    def _update():
        for setting, value in options.items():
            publish(f"pioreactor/{unit}/{experiment}/{job_name}/{setting}/set", value)

    return _update


def hours_to_seconds(hours: float) -> float:
    return hours * 60 * 60


def load_and_verify_profile_file(profile_filename: str) -> Profile:
    with open(profile_filename) as f:
        return decode(f.read(), type=Profile)


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


def execute_experiment_profile(profile_filename: str) -> None:
    unit = get_unit_name()
    experiment = get_latest_experiment_name()
    logger = create_logger("execute_experiment_profile")
    with publish_ready_to_disconnected_state(
        unit, experiment, "execute_experiment_profile"
    ) as state:
        profile = load_and_verify_profile_file(profile_filename)

        logger.info(
            f"Starting profile {profile.experiment_profile_name}, sourced from {profile_filename}."
        )

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
                        action.type,
                        action.options,
                        action.args,
                    ),
                )
                timers.append(t)

        # process specific jobs
        for unit_or_label in profile.pioreactors:
            unit = labels_to_units.get(unit_or_label, unit_or_label)
            jobs = profile.pioreactors[unit_or_label]["jobs"]
            for job in jobs:
                for action in jobs[job]["actions"]:
                    t = Timer(
                        hours_to_seconds(action.hours_elapsed),
                        execute_action(
                            unit, experiment, job, action.type, action.options, action.args
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
            if state.exit_event.is_set():
                # ended early
                for timer in timers:
                    timer.cancel()
                logger.debug("Finished execution early. Exiting.")
            else:
                logger.debug("Finished execution. Exiting.")


@click.command(name="execute_experiment_profile")
@click.argument("filename")
def click_execute_experiment_profile(filename: str) -> None:
    """
    (leader only) Run an experiment profile.
    """
    return execute_experiment_profile(filename)
