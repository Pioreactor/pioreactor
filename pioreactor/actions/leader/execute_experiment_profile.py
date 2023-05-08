# -*- coding: utf-8 -*-
from __future__ import annotations

import click
from msgspec.yaml import decode

from pioreactor.config import config
from pioreactor.config import get_active_workers_in_inventory
from pioreactor.logging import create_logger
from pioreactor.pubsub import subscribe
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.experiment_profiles.structs import Profile
from threading import Timer

from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def execute_action(job_name, unit, action, parameters=None):
    # Handle each action type accordingly
    if action == 'start':
        # start the job with the provided parameters
        start_job(job_name, unit, parameters)
    elif action == 'pause':
        # pause the job
        pause_job(job_name, unit)
    elif action == 'resume':
        # resume the job
        resume_job(job_name, unit)
    elif action == 'stop':
        # stop the job
        stop_job(job_name, unit)
    elif action == 'update':
        # update the job with the provided parameters
        update_job(job_name, unit, parameters)

def start_job(job_name, unit, parameters):
    print(f'Starting {job_name} with parameters: {parameters}')

def pause_job(job_name, unit):
    print(f'Pausing {job_name}')

def resume_job(job_name, unit):
    print(f'Resuming {job_name}')

def stop_job(job_name, unit):
    print(f'Stopping {job_name}')

def update_job(job_name, unit, parameters):
    print(f'Updating {job_name} with parameters: {parameters}')


def hours_to_seconds(hours: float) -> float:
    return hours * 60 * 60


def load_and_verify_profile_file(profile_filename: str) -> Profile:
    with open(profile_filename) as f:
        return decode(f.read(), type=Profile)

def execute_experiment_profile(profile_filename: str) -> None:

    unit = get_unit_name()
    experiment = ""
    logger = create_logger("execute_experiment_profile")
    with publish_ready_to_disconnected_state(unit, experiment, "execute_experiment_profile"):
        profile = load_and_verify_profile_file()


        # process global jobs










@click.command(name="backup_database")
@click.argument("filename")
def click_execute_experiment_profile(filename: str) -> None:
    """
    (leader only) Run a experiment profile.
    """
    return execute_experiment_profile(filename)