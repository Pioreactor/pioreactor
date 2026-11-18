# -*- coding: utf-8 -*-
"""
What a unit changes about itself to join or leave a cluster.

Joining: the leader's `pio workers add` registers the unit and sends its shared config
to `pio cluster join` for validation and installation.

Leaving: the leader's `DELETE /api/workers/<unit>` asks the unit's `POST /unit_api/cluster/leave`,
or the unit runs `pio cluster leave` itself. Both call `leave_cluster`.
"""
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

from pioreactor.config import config
from pioreactor.config import ConfigParserMod
from pioreactor.config import remove_config_values_in_file
from pioreactor.config import replace_or_append_config_entry
from pioreactor.config import resolve_global_config_path
from pioreactor.config import resolve_local_config_path
from pioreactor.config import set_config_value_in_file
from pioreactor.config import temporary_config_changes
from pioreactor.config import write_config_text
from pioreactor.unit_active import is_locally_active
from pioreactor.unit_active import report_active_to_leader
from pioreactor.unit_model import check_model_hardware
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
    shared_config.read(resolve_global_config_path(), encoding="utf-8")
    return shared_config


def standalone_config_path() -> Path:
    return resolve_global_config_path().with_name("config.ini.standalone")


def configured_leader() -> str:
    return _read_shared_config().get("cluster.topology", "leader_hostname", fallback="") or ""


def _incoming_config(config_text: str) -> tuple[ConfigParserMod, str, str]:
    incoming = ConfigParserMod(strict=False)
    incoming.read_string(config_text)
    hostname = incoming.get("cluster.topology", "leader_hostname", fallback=None)
    address = incoming.get("cluster.topology", "leader_address", fallback=None)
    if not hostname or not address or hostname == get_unit_name():
        raise RuntimeError("The incoming configuration must identify a different leader and its address.")
    return incoming, hostname, address


def activities_are_running() -> bool:
    with JobManager() as manager:
        return manager.count_running_jobs(include_long_running_jobs=False) > 0


def check_can_leave(stop_activities: bool = False, requested_by: str | None = None) -> None:
    """Raise if this unit can't leave its cluster. Callers check before telling the leader."""
    leader = configured_leader()
    if leader == get_unit_name():
        raise RuntimeError("This unit is its cluster's leader, so it can't leave it.")
    if requested_by is not None and requested_by != leader:
        # e.g. a leader dropping a unit that refused to join it.
        raise RuntimeError(f"This unit's leader is `{leader}`, not `{requested_by}`.")
    if not stop_activities and activities_are_running():
        raise RuntimeError("Stop activities before leaving the cluster.")


def clear_previous_leader_overrides(
    unit_config_path: Path, previous_broker_address: str | None = None
) -> None:
    """unit_config.ini overrides the shared config.ini, so remove the keys that point at a previous leader."""
    unit_config = ConfigParserMod(strict=False)
    unit_config.read(unit_config_path)
    previous_leader_address = unit_config.get("cluster.topology", "leader_address", fallback=None)

    stale = [("cluster.topology", "leader_address"), ("cluster.topology", "leader_hostname")]
    # A broker override can be deliberate (e.g. localhost), so only drop one that pointed at the previous leader.
    broker = unit_config.get("mqtt", "broker_address", fallback=None)
    if broker is not None and broker in (previous_leader_address, previous_broker_address):
        stale.append(("mqtt", "broker_address"))
    remove_config_values_in_file(unit_config_path, stale)


def point_clock_at_leader(leader_address: str, leader_time: int) -> None:
    _sudo("date", "-u", "--set", f"@{leader_time}")
    # One file we own, overwritten on every join, so a unit never keeps a previous leader as a time source.
    _sudo("tee", str(CHRONY_LEADER_SOURCE), input=f"server {leader_address} iburst prefer\n")


def _check_standalone_idle(shared_config: ConfigParserMod, unit: str) -> None:
    # Merging unit_config.ini into the caller's parser is deliberate: join then also drops its own
    # broker override (e.g. 127.0.0.1), which would otherwise keep this unit on its own broker.
    shared_config.read(resolve_local_config_path())
    database = Path(shared_config.get("storage", "database"))
    with closing(sqlite3.connect(database.absolute().as_uri() + "?mode=ro", uri=True)) as connection:
        if not connection.execute("SELECT 1 FROM workers WHERE pioreactor_unit = ?", (unit,)).fetchone():
            raise RuntimeError("Only a standalone leader-worker can join another cluster.")
        if connection.execute("SELECT 1 FROM workers WHERE pioreactor_unit != ? LIMIT 1", (unit,)).fetchone():
            raise RuntimeError("Remove this unit's workers before joining another cluster.")
        if connection.execute(
            "SELECT 1 FROM experiment_worker_assignments WHERE pioreactor_unit = ?", (unit,)
        ).fetchone():
            raise RuntimeError("Unassign this unit from its experiment before joining a cluster.")


def join_cluster(
    config_text: str,
    leader_time: int,
    model_name: str | None = None,
    model_version: str | None = None,
) -> None:
    """Validate the staged config and current membership before changing the active shared config."""
    incoming, leader, leader_address = _incoming_config(config_text)
    active_path = resolve_global_config_path()
    current = _read_shared_config()
    current_leader = current.get("cluster.topology", "leader_hostname", fallback=None)
    unit = get_unit_name()
    if activities_are_running():
        raise RuntimeError("Stop activities before joining a cluster.")
    if current_leader and current_leader not in (unit, leader):
        raise RuntimeError(f"This unit already belongs to `{current_leader}`. Leave that cluster first.")
    if current_leader == unit:
        _check_standalone_idle(current, unit)

    if model_name is not None and model_version is not None:
        save_local_model(model_name, model_version)
        check_model_hardware(model_name, model_version)

    if current_leader == unit:
        write_config_text(standalone_config_path(), active_path.read_text(encoding="utf-8"))
    point_clock_at_leader(leader_address, leader_time)
    clear_previous_leader_overrides(
        resolve_local_config_path(), current.get("mqtt", "broker_address", fallback=None)
    )
    write_config_text(active_path, config_text)

    # This CLI process may still have the previous config loaded.
    with temporary_config_changes(
        config,
        [
            ("ui", "port", incoming.get("ui", "port", fallback="80")),
            ("ui", "proto", incoming.get("ui", "proto", fallback="http")),
        ],
    ):
        if not report_active_to_leader(leader_address, is_locally_active()):
            raise RuntimeError(
                f"Unable to report whether this unit is active to the leader at {leader_address}."
            )
        assigned = get_local_model()
        if assigned is not None and not report_model_to_leader(leader_address, *assigned):
            raise RuntimeError(f"Unable to report this unit's model to the leader at {leader_address}.")


def _standalone_config_for(unit: str) -> str:
    config_text = standalone_config_path().read_text(encoding="utf-8")
    for section, key, value in (
        ("cluster.topology", "leader_hostname", unit),
        ("cluster.topology", "leader_address", f"{unit}.local"),
        ("mqtt", "broker_address", f"{unit}.local"),
    ):
        config_text = replace_or_append_config_entry(config_text, section, key, value)
    ConfigParserMod(strict=False).read_string(config_text)
    return config_text


def leave_cluster(stop_activities: bool = False) -> bool:
    """
    Undo `join_cluster`. Keeps this unit's model, calibrations, estimators and unit settings.
    The caller reboots afterwards, so no service keeps the old leader in memory.
    """
    current = _read_shared_config()
    unit = get_unit_name()
    if current.get("cluster.topology", "leader_hostname", fallback=None) == unit:
        # The CLI and leader can both request the same leave.
        return False
    check_can_leave(stop_activities)
    # Only a unit that joined from standalone (or a leader-capable unit seeded on update) has this file.
    standalone = _standalone_config_for(unit) if standalone_config_path().exists() else None

    with JobManager() as manager:
        manager.kill_jobs(all_jobs=True)
    _sudo("rm", "-f", str(CHRONY_LEADER_SOURCE))
    if standalone is None:
        resolve_global_config_path().unlink(missing_ok=True)
    else:
        # Restore the loopback overrides that leader images set and joining removed.
        for section, key in (("cluster.topology", "leader_address"), ("mqtt", "broker_address")):
            set_config_value_in_file(resolve_local_config_path(), section, key, "127.0.0.1")
        write_config_text(resolve_global_config_path(), standalone)
    return True
