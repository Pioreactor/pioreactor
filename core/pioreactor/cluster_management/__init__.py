# -*- coding: utf-8 -*-
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from time import sleep

import click
from msgspec.json import decode as loads
from msgspec.json import encode as dumps
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.config import config
from pioreactor.config import leader_address
from pioreactor.config import leader_hostname
from pioreactor.exc import BashScriptError
from pioreactor.http_response import summarize_error_response
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


def get_workers_in_inventory() -> tuple[pt.Unit, ...]:
    result = get_from_leader("/api/workers")
    result.raise_for_status()
    return tuple(worker["pioreactor_unit"] for worker in result.json())


def get_active_workers_in_inventory() -> tuple[pt.Unit, ...]:
    result = get_from_leader("/api/workers")
    result.raise_for_status()
    return tuple(worker["pioreactor_unit"] for worker in result.json() if bool(worker["is_active"]))


def get_active_workers_in_experiment(experiment: pt.Experiment) -> tuple[pt.Unit, ...]:
    result = get_from_leader(f"/api/experiments/{experiment}/workers")
    result.raise_for_status()
    return tuple(worker["pioreactor_unit"] for worker in result.json() if bool(worker["is_active"]))


def get_workers_in_experiment(experiment: pt.Experiment) -> tuple[pt.Unit, ...]:
    result = get_from_leader(f"/api/experiments/{experiment}/workers")
    result.raise_for_status()
    return tuple(worker["pioreactor_unit"] for worker in result.json())


def _unique_worker_add_address_candidates(hostname: str, address: str | None) -> tuple[str, ...]:
    if address:
        return (address,)

    candidates: list[str | None] = [config.get("cluster.addresses", hostname, fallback=None)]
    try:
        candidates.extend(
            worker.ipv4_address
            for worker in networking.discover_workers_on_network(terminate=True)
            if worker.hostname == hostname
        )
    except OSError:
        pass

    candidates.append(networking.add_local(hostname))

    unique_candidates: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique_candidates:
            unique_candidates.append(candidate)

    return tuple(unique_candidates)


def _find_reachable_worker_add_address(hostname: str, candidates: tuple[str, ...]) -> str | None:
    checks, max_checks = 0, 15
    sleep_time = 3

    while checks < max_checks:
        for candidate in candidates:
            if networking.is_address_on_network(candidate, timeout=2):
                return candidate

        checks += 1
        click.echo(f"`{hostname}` not found on network - checking again.")
        if checks < max_checks:
            sleep(sleep_time)

    return None


@click.command(name="add", short_help="add a pioreactor worker")
@click.argument("hostname")
@click.option("--password", "-p", default="raspberry")
@click.option(
    "--model-name",
    "-m",
)
@click.option(
    "--model-version",
    "-v",
)
@click.option("--address", "-a")
def add_worker(
    hostname: str, password: str, model_name: str | None, model_version: str | None, address: str | None
) -> None:
    """
    Add a new pioreactor worker to the cluster. The pioreactor should already have the worker image installed and is turned on.
    """
    # validate combo against registry
    from pioreactor.models import get_registered_models

    registered_models = get_registered_models()

    if model_name and model_version and ((model_name, model_version) not in registered_models):
        click.echo(
            f"Invalid model/version: {model_name} v{model_version}."
            f" Valid options: {sorted(registered_models.keys())}"
        )
        raise click.Abort()

    if hostname.endswith(".local"):
        # exit with message
        click.echo("Please provide the hostname without the `.local` suffix.")
        raise click.Abort()

    if hostname == whoami.get_unit_name():
        click.echo(
            "You cannot add the current leader Pioreactor as a worker this way. Email us at support@pioreactor.com"
        )
        raise click.Abort()

    import socket

    logger = create_logger(
        "add_pioreactor",
        unit=whoami.get_unit_name(),
        experiment=whoami.UNIVERSAL_EXPERIMENT,
    )
    logger.info(f"Adding new pioreactor {hostname} to cluster.")

    address_candidates = _unique_worker_add_address_candidates(hostname, address)

    if not whoami.is_testing_env():
        with catchtime() as elapsed:
            possible_address = _find_reachable_worker_add_address(hostname, address_candidates)
        if possible_address is None:
            logger.error(
                f"`{hostname}` not found on network after {round(elapsed())} seconds. "
                f"Checked: {', '.join(address_candidates)}. Check that i) the name is correct, ii) worker is powered on, iii) any WiFi credentials to the network are correct."
            )
            raise click.Abort()

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

    logger.notice(f"New pioreactor {hostname} successfully added to cluster.")


@click.command(name="remove", short_help="remove a pioreactor worker")
@click.argument("worker")
def remove_worker(worker: pt.Unit) -> None:
    try:
        r = delete_from_leader(f"/api/workers/{worker}")
        r.raise_for_status()
    except HTTPErrorStatus:
        if r.status_code >= 500:
            click.echo("Server error. Could not complete. See UI logs.")
        else:
            click.echo(f"Worker {worker} not present to be removed. Check hostname.")
        raise click.Abort()
    except HTTPException:
        click.echo(f"Not able to connect to leader's backend at {leader_address}.")
        raise click.Abort()
    else:
        click.echo(f"Removed {worker} from cluster.")  # this needs to shutdown the worker too???


@click.command(name="assign", short_help="assign a pioreactor worker")
@click.argument("worker")
@click.argument("experiment")
def assign_worker_to_experiment(worker: pt.Unit, experiment: pt.Experiment) -> None:
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
        raise click.Abort()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        raise click.Abort()
    else:
        click.echo(f"Assigned {worker} to {experiment}")


@click.command(name="unassign", short_help="unassign a pioreactor worker")
@click.argument("worker")
@click.argument("experiment")
def unassign_worker_from_experiment(worker: pt.Unit, experiment: pt.Experiment) -> None:
    try:
        r = delete_from_leader(
            f"/api/experiments/{experiment}/workers/{worker}",
        )
        r.raise_for_status()
    except HTTPErrorStatus:
        click.echo("Error")
        raise click.Abort()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        raise click.Abort()
    else:
        click.echo(f"Unassigned {worker} from {experiment}")


@click.command(name="update-active", short_help="change active of worker")
@click.argument("hostname")
@click.argument("active", type=click.IntRange(0, 1))
def update_active(worker: pt.Unit, active: int) -> None:
    try:
        r = put_into_leader(
            f"/api/workers/{worker}/is_active",
            json={"is_active": active},
        )
        r.raise_for_status()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        raise click.Abort()
    else:
        click.echo(f"Updated {worker}'s active to {bool(active)}")


@click.command(name="update-model", short_help="update worker model metadata")
@click.argument("worker")
@click.option("--model-name", "-m", required=True)
@click.option("--model-version", "-v", required=True)
def update_model(worker: pt.Unit, model_name: str, model_version: str) -> None:
    from pioreactor.models import get_registered_models

    registered_models = get_registered_models()

    if (model_name, model_version) not in registered_models:
        click.echo(
            f"Invalid model/version: {model_name} v{model_version}."
            f" Valid options: {sorted(registered_models.keys())}"
        )
        raise click.Abort()

    try:
        r = put_into_leader(
            f"/api/workers/{worker}/model",
            json={"model_name": model_name, "model_version": model_version},
        )
        r.raise_for_status()
    except HTTPErrorStatus:
        if r.status_code >= 500:
            click.echo("Server error. Could not complete. See UI logs.")
        else:
            click.echo("Not valid data. Check model name or version.")
        raise click.Abort()
    except HTTPException:
        click.echo("Not able to connect to leader's backend.")
        raise click.Abort()
    else:
        click.echo(f"Updated {worker} to {model_name} v{model_version}.")


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

    for worker in discover_workers_on_network(terminate):
        click.echo(f"{worker.hostname}\t{worker.ipv4_address}")


@click.command(name="status", short_help="report information on the cluster")
def cluster_status() -> None:
    import socket

    def get_metadata(hostname: str) -> tuple[str, str, bool, str, str]:
        resolved_address = "localhost"
        # get ip
        if whoami.get_unit_name() == hostname:
            ip = networking.get_ip()
            resolved_address = "localhost"
        else:
            try:
                resolved_address = networking.resolve_to_address(hostname)
                ip = socket.gethostbyname(resolved_address)
            except (OSError, Exception):
                ip = "unknown"
                resolved_address = hostname

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

        # is web API reachable?
        web_ok = False
        try:
            web_resp = get_from(resolved_address, "/unit_api/health", timeout=2)
            web_ok = web_resp.ok
        except HTTPException:
            web_ok = False

        if state == "unknown" and web_ok:
            state = "unknown(mqtt)"

        # get version
        try:
            r = get_from(resolved_address, "/unit_api/versions/app", timeout=2)
            r.raise_for_status()
            app_version = r.json()["version"]
        except HTTPException:
            app_version = "unknown(api)" if web_ok else "unknown"

        # Prefer the unit API health check; ICMP is a fallback for hosts whose webserver is unavailable.
        reachable = web_ok or networking.is_reachable(resolved_address)

        # get experiment
        try:
            r = get_from_leader(f"/api/workers/{hostname}/experiment")
            r.raise_for_status()
            experiment = r.json()["experiment"]
        except HTTPException:
            experiment = "unknown"

        return ip, state, reachable, app_version, experiment

    def display_data_for(worker: dict[str, str]) -> str:
        hostname, is_active = worker["pioreactor_unit"], worker["is_active"]

        ip, state, reachable, version, experiment = get_metadata(hostname)

        state_lower = state.lower()
        if state_lower in ("ready", "init"):
            state_color = "green"
        elif state_lower.startswith("unknown"):
            state_color = "yellow"
        else:
            state_color = "red"
        statef = click.style(f"{state:15s}", fg=state_color, bold=True)
        ipf = f"{ip if (ip is not None) else 'unknown':20s}"

        is_leader_value = "Y" if hostname == leader_hostname else ""
        is_leader_color = "green" if is_leader_value == "Y" else "red"
        is_leaderf = click.style(f"{is_leader_value:15s}", fg=is_leader_color, bold=True)
        hostnamef = f"{hostname:20s}"
        reachable_value = "Y" if reachable else "N"
        reachable_color = "green" if reachable else "red"
        reachablef = click.style(f"{reachable_value:14s}", fg=reachable_color, bold=True)
        versionf = f"{version:15s}"
        is_active_value = "Y" if is_active else "N"
        is_active_color = "green" if is_active else "red"
        is_activef = click.style(f"{is_active_value:15s}", fg=is_active_color, bold=True)
        experimentf = f"{experiment:15s}"

        return f"{hostnamef} {is_leaderf} {ipf} {statef} {is_activef} {reachablef} {versionf} {experimentf}"

    response = get_from_leader("/api/workers")
    try:
        response.raise_for_status()
    except HTTPErrorStatus as error:
        raise click.ClickException(f"Unable to get workers. {summarize_error_response(response)}") from error
    workers = response.json()

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
