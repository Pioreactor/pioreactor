# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
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
from pioreactor.pubsub import get_from_leader
from pioreactor.pubsub import put_into_leader
from pioreactor.utils import networking
from pioreactor.utils.timing import catchtime


def get_workers_in_inventory() -> tuple[str, ...]:
    result = get_from_leader("/api/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json())


def get_active_workers_in_inventory() -> tuple[str, ...]:
    result = get_from_leader("/api/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json() if bool(worker["is_active"]))


def get_workers_in_experiment(experiment: str) -> tuple[str, ...]:
    result = get_from_leader(f"/api/experiments/{experiment}/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json())


def get_active_workers_in_experiment(experiment: str) -> tuple[str, ...]:
    result = get_from_leader(f"/api/experiments/{experiment}/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json() if bool(worker["is_active"]))


@click.command(name="add", short_help="add a pioreactor worker")
@click.argument("hostname")
@click.option("--password", "-p", default="raspberry")
@click.option("--version", "-v", default="1.1")
@click.option("--model", "-m", default="pioreactor_20ml")
def add_worker(hostname: str, password: str, version: str, model: str) -> None:
    """
    Add a new pioreactor worker to the cluster. The pioreactor should already have the worker image installed and is turned on.
    """

    import socket

    logger = create_logger(
        "add_pioreactor",
        unit=whoami.get_unit_name(),
        experiment=whoami.UNIVERSAL_EXPERIMENT,
    )
    logger.info(f"Adding new pioreactor {hostname} to cluster.")

    hostname = hostname.removesuffix(".local")
    hostname_dot_local = hostname + ".local"

    assert model == "pioreactor_20ml"

    # check to make sure <hostname>.local is on network
    checks, max_checks = 0, 15
    sleep_time = 3

    if not whoami.is_testing_env():
        with catchtime() as elapsed:
            while not networking.is_hostname_on_network(hostname_dot_local):
                checks += 1
                try:
                    socket.gethostbyname(hostname_dot_local)
                except socket.gaierror:
                    sleep(sleep_time)
                    click.echo(f"`{hostname}` not found on network - checking again.")
                    if checks >= max_checks:
                        logger.error(
                            f"`{hostname}` not found on network after {round(elapsed())} seconds. Check that you provided the right i) the name is correct, ii) worker is powered on, iii) any WiFi credentials to the network are correct."
                        )
                        raise click.Abort()

        res = subprocess.run(
            [
                "bash",
                "/usr/local/bin/add_new_pioreactor_worker_from_leader.sh",
                hostname,
                password,
                version,
                model,
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
            json={"pioreactor_unit": hostname},
        )
        r.raise_for_status()
    except HTTPErrorStatus:
        if r.status_code >= 500:
            click.echo("Server error. Could not complete.")
        else:
            logger.error("Did not add worker to backend")
        raise HTTPException("Did not add worker to backend")
    except HTTPException:
        logger.error("Could not connect to leader's webserver")
        raise HTTPException("Could not connect to leader's webserver")

    logger.notice(f"New pioreactor {hostname} successfully added to cluster.")  # type: ignore


@click.command(name="remove", short_help="remove a pioreactor worker")
@click.argument("hostname")
def remove_worker(hostname: str) -> None:
    try:
        r = delete_from_leader(f"/api/workers/{hostname}")
        r.raise_for_status()
    except HTTPErrorStatus:
        if r.status_code >= 500:
            click.echo("Server error. Could not complete.")
        else:
            click.echo(f"Worker {hostname} not present to be removed. Check hostname.")
        click.Abort()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        click.Abort()
    else:
        click.echo(f"Removed {hostname} from cluster.")  # this needs to shutdown the worker too???


@click.command(name="assign", short_help="assign a pioreactor worker")
@click.argument("hostname")
@click.argument("experiment")
def assign_worker_to_experiment(hostname: str, experiment: str) -> None:
    try:
        r = put_into_leader(
            f"/api/experiments/{experiment}/workers",
            json={"pioreactor_unit": hostname},
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
        click.echo(f"Assigned {hostname} to {experiment}")


@click.command(name="unassign", short_help="unassign a pioreactor worker")
@click.argument("hostname")
@click.argument("experiment")
def unassign_worker_from_experiment(hostname: str, experiment: str) -> None:
    try:
        r = delete_from_leader(
            f"/api/experiments/{experiment}/workers/{hostname}",
        )
        r.raise_for_status()
    except HTTPErrorStatus:
        click.echo("Error")
        click.Abort()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        click.Abort()
    else:
        click.echo(f"Unassigned {hostname} from {experiment}")


@click.command(name="update-active", short_help="change active of worker")
@click.argument("hostname")
@click.argument("active", type=click.IntRange(0, 1))
def update_active(hostname: str, active: int) -> None:
    try:
        r = put_into_leader(
            f"/api/workers/{hostname}/is_active",
            json={"is_active": active},
        )
        r.raise_for_status()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        click.Abort()
    else:
        click.echo(f"Updated {hostname}'s active to {bool(active)}")


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
    """
    Note that this only looks at the current cluster as defined in config.ini.
    """
    import socket
    from pioreactor import pubsub

    def get_metadata(hostname):
        # get ip
        if whoami.get_unit_name() == hostname:
            ip = networking.get_ip()
        else:
            try:
                ip = socket.gethostbyname(networking.add_local(hostname))
            except OSError:
                ip = "unknown"

        # get state
        result = pubsub.subscribe(
            f"pioreactor/{hostname}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/$state",
            timeout=1,
            name="CLI",
        )
        if result:
            state = result.payload.decode()
        else:
            state = "unknown"

        # get version
        result = pubsub.subscribe(
            f"pioreactor/{hostname}/{whoami.UNIVERSAL_EXPERIMENT}/monitor/versions",
            timeout=1,
            name="CLI",
        )
        if result:
            app_version = loads(result.payload.decode())["app"]
        else:
            app_version = "unknown"

        # is reachable?
        reachable = networking.is_reachable(networking.add_local(hostname))

        # get experiment
        try:
            result = get_from_leader(f"/api/workers/{hostname}/experiment")
            experiment = result.json()["experiment"]
        except Exception:
            experiment = ""

        return ip, state, reachable, app_version, experiment

    def display_data_for(worker: dict[str, str]) -> bool:
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

        click.echo(
            f"{hostnamef} {is_leaderf} {ipf} {statef} {is_activef} {reachablef} {versionf} {experimentf}"
        )
        return reachable & (state == "ready")

    workers = get_from_leader("/api/workers").json()
    n_workers = len(workers)

    click.secho(
        f"{'Unit / hostname':20s} {'Is leader?':15s} {'IP address':20s} {'State':15s} {'Active?':15s} {'Reachable?':14s} {'Version':15s} {'Experiment':15s}",
        bold=True,
    )
    if n_workers == 0:
        return

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        results = executor.map(display_data_for, workers)

    if not all(results):
        raise click.Abort()
