# -*- coding: utf-8 -*-
"""
What a unit changes about itself to join or leave a cluster.

Joining: the leader's `pio workers add` registers the unit, copies its shared config.ini
here, then runs `pio cluster join`, which calls `join_cluster`.

Leaving: the leader's `DELETE /api/workers/<unit>` asks the unit's `POST /unit_api/cluster/leave`,
or the unit runs `pio cluster leave` itself. Both call `leave_cluster`.
"""
import subprocess
from pathlib import Path

from pioreactor.config import ConfigParserMod
from pioreactor.config import remove_config_values_in_file
from pioreactor.config import resolve_global_config_path
from pioreactor.config import resolve_local_config_path
from pioreactor.unit_model import get_local_model
from pioreactor.unit_model import report_model_to_leader
from pioreactor.unit_model import save_local_model
from pioreactor.utils.job_manager import JobManager
from pioreactor.whoami import get_unit_name

CHRONY_LEADER_SOURCE = Path("/etc/chrony/conf.d/pioreactor-leader.conf")


def _sudo(*args: str, input: str | None = None) -> None:
    subprocess.run(["sudo", *args], input=input, text=True, check=True, stdout=subprocess.DEVNULL)


def _read_shared_config() -> ConfigParserMod:
    # Read the file: this process's config may predate the leader's copy, or its removal.
    shared_config = ConfigParserMod(strict=False)
    shared_config.read(resolve_global_config_path())
    return shared_config


def activities_are_running() -> bool:
    with JobManager() as manager:
        return manager.count_running_jobs(include_long_running_jobs=False) > 0


def clear_previous_leader_overrides(unit_config_path: Path) -> None:
    """unit_config.ini overrides the shared config.ini, so remove the keys that point at a previous leader."""
    unit_config = ConfigParserMod(strict=False)
    unit_config.read(unit_config_path)
    previous_leader_address = unit_config.get("cluster.topology", "leader_address", fallback=None)

    stale = [("cluster.topology", "leader_address"), ("cluster.topology", "leader_hostname")]
    # A broker override can be deliberate (e.g. localhost), so only drop one that pointed at the previous leader.
    if previous_leader_address is not None and (
        unit_config.get("mqtt", "broker_address", fallback=None) == previous_leader_address
    ):
        stale.append(("mqtt", "broker_address"))
    remove_config_values_in_file(unit_config_path, stale)


def point_clock_at_leader(leader_address: str, leader_time: int) -> None:
    _sudo("date", "-u", "--set", f"@{leader_time}")
    # One file we own, overwritten on every join, so a unit never keeps a previous leader as a time source.
    _sudo("tee", str(CHRONY_LEADER_SOURCE), input=f"server {leader_address} iburst prefer\n")


def join_cluster(leader_time: int, model_name: str | None = None, model_version: str | None = None) -> None:
    """
    Point this unit at the leader named in its shared config.ini, and report its model there.
    """
    if model_name is not None and model_version is not None:
        # First, since it's the step most likely to fail (unknown model, jobs running).
        save_local_model(model_name, model_version)
        from pioreactor.web.tasks import check_model_hardware

        # Run it now: Huey's queue is on tmpfs, and the leader reboots this unit next.
        check_model_hardware.call_local(model_name, model_version)

    leader_address = _read_shared_config().get("cluster.topology", "leader_address")

    clear_previous_leader_overrides(resolve_local_config_path())
    point_clock_at_leader(leader_address, leader_time)

    assigned = get_local_model()
    if assigned is None:
        return
    assigned_model_name, assigned_model_version = assigned
    if not report_model_to_leader(leader_address, assigned_model_name, assigned_model_version):
        raise RuntimeError(f"Unable to report this unit's model to the leader at {leader_address}.")


def _reset_shared_config() -> None:
    # Today a unit that left is unconfigured, waiting to be added again. With standalone
    # images, this is where it would point its shared config at itself instead.
    resolve_global_config_path().unlink(missing_ok=True)


def leave_cluster(stop_activities: bool = False) -> None:
    """
    Undo `join_cluster`. Keeps this unit's model, calibrations, estimators and unit_config.ini.
    The caller reboots afterwards, so no service keeps the old leader in memory.
    """
    if _read_shared_config().get("cluster.topology", "leader_hostname", fallback=None) == get_unit_name():
        raise RuntimeError("This unit is its cluster's leader, so it can't leave it.")
    if not stop_activities and activities_are_running():
        raise RuntimeError("Stop activities before leaving the cluster.")

    with JobManager() as manager:
        manager.kill_jobs(all_jobs=True)
    _sudo("rm", "-f", str(CHRONY_LEADER_SOURCE))
    _reset_shared_config()
