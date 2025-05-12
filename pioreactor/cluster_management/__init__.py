# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from time import sleep

import click
from msgspec.json import decode as loads
from msgspec.json import encode as dumps

from pioreactor import whoami
from pioreactor.config import leader_address
from pioreactor.config import leader_hostname
from pioreactor.exc import BashScriptError
from pioreactor.logging import create_logger
from pioreactor.mureq import HTTPErrorStatus
from pioreactor.mureq import HTTPException
from pioreactor.pubsub import delete_from_leader
from pioreactor.pubsub import get_from
from pioreactor.pubsub import get_from_leader
from pioreactor.pubsub import put_into_leader
from pioreactor.pubsub import subscribe
from pioreactor.utils import networking
from pioreactor.utils.timing import catchtime


def get_workers_in_inventory() -> tuple[str, ...]:
    result = get_from_leader("/api/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json())


def get_active_workers_in_inventory() -> tuple[str, ...]:
    result = get_from_leader("/api/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json() if bool(worker["is_active"]))


def get_active_workers_in_experiment(experiment: str) -> tuple[str, ...]:
    result = get_from_leader(f"/api/experiments/{experiment}/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json() if bool(worker["is_active"]))


@click.command(name="add", short_help="add a pioreactor worker")
@click.argument("hostname")
@click.option("--password", "-p", default="raspberry")
@click.option("--model-name", "-m", type=click.Choice(["pioreactor_20ml", "pioreactor_40ml"]), required=True)
@click.option("--model-version", "-v", required=True, type=click.Choice(["1.0", "1.1"]))
@click.option("--address", "-a")
def add_worker(
    hostname: str, password: str, model_name: str, model_version: str, address: str | None
) -> None:
    """
    Add a new pioreactor worker to the cluster. The pioreactor should already have the worker image installed and is turned on.
    """
    if hostname.endswith(".local"):
        # exit with message
        click.echo("Please provide the hostname without the `.local` suffix.")
        raise click.Abort()

    import socket

    logger = create_logger(
        "add_pioreactor",
        unit=whoami.get_unit_name(),
        experiment=whoami.UNIVERSAL_EXPERIMENT,
    )
    logger.info(f"Adding new pioreactor {hostname} to cluster.")

    possible_address = address or networking.resolve_to_address(hostname)

    # check to make sure <hostname>.local is on network
    checks, max_checks = 0, 15
    sleep_time = 3

    if not whoami.is_testing_env():
        with catchtime() as elapsed:
            while not networking.is_address_on_network(possible_address):
                checks += 1
                click.echo(f"`{hostname}` not found on network - checking again.")
                if checks >= max_checks:
                    logger.error(
                        f"`{hostname}` not found on network after {round(elapsed())} seconds. Check that you provided the right i) the name is correct, ii) worker is powered on, iii) any WiFi credentials to the network are correct."
                    )
                    sys.exit(1)
                sleep(sleep_time)

        res = subprocess.run(
            [
                "bash",
                "/usr/local/bin/add_new_pioreactor_worker_from_leader.sh",
                hostname,
                password,
                possible_address,
            ],
            capture_output=True,
            text=True,
        )
        if res.returncode > 0:
            logger.error(res.stderr)
            raise BashScriptError(res.stderr)

    try:
        r = put_into_leader(
            "/api/workers",
            json={"pioreactor_unit": hostname, "model_name": model_name, "model_version": model_version},
        )
        r.raise_for_status()
    except HTTPErrorStatus:
        if r.status_code >= 500:
            logger.error("Server error. Could not complete. See UI logs")
        else:
            logger.error(f"Did not add worker {hostname} to backend.")
        raise HTTPException(f"Did not add worker {hostname} to backend.")
    except HTTPException:
        logger.error(f"Not able to connect to leader's backend at {leader_address}.")
        raise HTTPException(f"Not able to connect to leader's backend at {leader_address}.")

    logger.notice(f"New pioreactor {hostname} successfully added to cluster.")  # type: ignore


@click.command(name="remove", short_help="remove a pioreactor worker")
@click.argument("worker")
def remove_worker(worker: str) -> None:
    try:
        r = delete_from_leader(f"/api/workers/{worker}")
        r.raise_for_status()
    except HTTPErrorStatus:
        if r.status_code >= 500:
            click.echo("Server error. Could not complete. See UI logs.")
        else:
            click.echo(f"Worker {worker} not present to be removed. Check hostname.")
        click.Abort()
    except HTTPException:
        click.echo(f"Not able to connect to leader's backend at {leader_address}.")
        click.Abort()
    else:
        click.echo(f"Removed {worker} from cluster.")  # this needs to shutdown the worker too???


@click.command(name="assign", short_help="assign a pioreactor worker")
@click.argument("worker")
@click.argument("experiment")
def assign_worker_to_experiment(worker: str, experiment: str) -> None:
    try:
        r = put_into_leader(
            f"/api/experiments/{experiment}/workers",
            json={"pioreactor_unit": worker},
        )
        r.raise_for_status()
    except HTTPErrorStatus:
        if r.status_code >= 500:
            click.echo("Server error. Could not complete.")
        else:
            click.echo("Not valid data. Check hostname or experiment.")
        click.Abort()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        click.Abort()
    else:
        click.echo(f"Assigned {worker} to {experiment}")


@click.command(name="unassign", short_help="unassign a pioreactor worker")
@click.argument("worker")
@click.argument("experiment")
def unassign_worker_from_experiment(worker: str, experiment: str) -> None:
    try:
        r = delete_from_leader(
            f"/api/experiments/{experiment}/workers/{worker}",
        )
        r.raise_for_status()
    except HTTPErrorStatus:
        click.echo("Error")
        click.Abort()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        click.Abort()
    else:
        click.echo(f"Unassigned {worker} from {experiment}")


@click.command(name="update-active", short_help="change active of worker")
@click.argument("hostname")
@click.argument("active", type=click.IntRange(0, 1))
def update_active(worker: str, active: int) -> None:
    try:
        r = put_into_leader(
            f"/api/workers/{worker}/is_active",
            json={"is_active": active},
        )
        r.raise_for_status()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        click.Abort()
    else:
        click.echo(f"Updated {worker}'s active to {bool(active)}")


@click.command(
    name="discover",
    short_help="discover all pioreactor workers on the network",
)
@click.option(
    "-t",
    "--terminate",
    is_flag=True,
    help="Terminate after dumping a more or less complete list",
)
def discover_workers(terminate: bool) -> None:
    from pioreactor.utils.networking import discover_workers_on_network

    for hostname in discover_workers_on_network(terminate):
        click.echo(hostname)


@click.command(name="status", short_help="report information on the cluster")
def cluster_status() -> None:
    import socket

    def get_metadata(hostname):
        # get ip
        if whoami.get_unit_name() == hostname:
            ip = networking.get_ip()
        else:
            try:
                # TODO: we can get this from MQTT, too?
                ip = socket.gethostbyname(networking.resolve_to_address(hostname))
            except (OSError, Exception):
                ip = "unknown"

        # get state
        result = subscribe(
            f"pioreactor/{hostname}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/$state",
            timeout=1,
            name="CLI",
        )
        if result:
            state = result.payload.decode()
        else:
            state = "unknown"

        # get version
        try:
            r = get_from(networking.resolve_to_address(hostname), "/unit_api/versions/app")
            r.raise_for_status()
            app_version = r.json()["version"]
        except HTTPException:
            app_version = "unknown"

        # is reachable? # TODO: change to webserver?
        reachable = networking.is_reachable(networking.resolve_to_address(hostname))

        # get experiment
        try:
            r = get_from_leader(f"/api/workers/{hostname}/experiment")
            r.raise_for_status()
            experiment = r.json()["experiment"]
        except HTTPException:
            experiment = ""

        return ip, state, reachable, app_version, experiment

    def display_data_for(worker: dict[str, str]) -> str:
        hostname, is_active = worker["pioreactor_unit"], worker["is_active"]

        ip, state, reachable, version, experiment = get_metadata(hostname)

        statef = click.style(f"{state:15s}", fg="green" if state in ("ready", "init") else "red")
        ipf = f"{ip if (ip is not None) else 'unknown':20s}"

        is_leaderf = f"{('Y' if hostname==leader_hostname else 'N'):15s}"
        hostnamef = f"{hostname:20s}"
        reachablef = f"{(click.style('Y', fg='green') if reachable else click.style('N', fg='red')):23s}"
        versionf = f"{version:15s}"
        is_activef = f"{(click.style('Y', fg='green') if is_active else click.style('N', fg='red')):24s}"
        experimentf = f"{experiment:15s}"

        return f"{hostnamef} {is_leaderf} {ipf} {statef} {is_activef} {reachablef} {versionf} {experimentf}"

    workers = get_from_leader("/api/workers").json()

    n_workers = len(workers)

    click.secho(
        f"{'Name':20s} {'Is leader?':15s} {'IP address':20s} {'State':15s} {'Active?':15s} {'Reachable?':14s} {'Version':15s} {'Experiment':15s}",
        bold=True,
    )
    if n_workers == 0:
        return

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        results = executor.map(display_data_for, workers)
        for result in results:
            click.echo(result)

    return
