# -*- coding: utf-8 -*-
"""
What a unit changes about itself to join a cluster.

The leader's `pio workers add` registers the unit, copies its shared config.ini here,
then runs `pio join-cluster`, which calls `join_cluster`.
"""
import subprocess
from pathlib import Path

from iniparse import INIConfig  # type: ignore[import-untyped]
from pioreactor.config import ConfigParserMod
from pioreactor.config import resolve_global_config_path
from pioreactor.config import resolve_local_config_path
from pioreactor.config import write_config_text
from pioreactor.unit_model import get_local_model
from pioreactor.unit_model import report_model_to_leader
from pioreactor.unit_model import save_local_model

CHRONY_LEADER_SOURCE = Path("/etc/chrony/conf.d/pioreactor-leader.conf")


def _sudo(*args: str, input: str | None = None) -> None:
    subprocess.run(["sudo", *args], input=input, text=True, check=True, stdout=subprocess.DEVNULL)


def clear_previous_leader_overrides(unit_config_path: Path) -> None:
    """unit_config.ini overrides the shared config.ini, so remove the keys that point at a previous leader."""
    if not unit_config_path.is_file():
        return

    with unit_config_path.open(encoding="utf-8") as file:
        # iniparse, unlike configparser, keeps the file's comments and layout when written back.
        unit_config = INIConfig(file)
    overrides = {
        section: {key: unit_config[section][key] for key in unit_config[section]} for section in unit_config
    }

    topology = overrides.get("cluster.topology", {})
    stale = [("cluster.topology", key) for key in ("leader_address", "leader_hostname") if key in topology]
    # A broker override can be deliberate (e.g. localhost), so only drop one that pointed at the previous leader.
    if (
        "leader_address" in topology
        and overrides.get("mqtt", {}).get("broker_address") == topology["leader_address"]
    ):
        stale.append(("mqtt", "broker_address"))

    for section, key in stale:
        del unit_config[section][key]
    if stale:
        write_config_text(unit_config_path, str(unit_config))


def point_clock_at_leader(leader_address: str, leader_time: int) -> None:
    _sudo("date", "-u", "--set", f"@{leader_time}")
    # One file we own, overwritten on every join, so a unit never keeps a previous leader as a time source.
    _sudo("tee", str(CHRONY_LEADER_SOURCE), input=f"server {leader_address} iburst prefer\n")


def join_cluster(leader_time: int, model: tuple[str, str] | None = None) -> tuple[str, str] | None:
    """
    Point this unit at the leader named in its shared config.ini, and report its model
    there. Returns the reported model, or None if the unit has none.
    """
    if model is not None:
        # First, since it's the step most likely to fail (unknown model, jobs running).
        save_local_model(*model)
        from pioreactor.web.tasks import check_model_hardware

        # Run it now: Huey's queue is on tmpfs, and the leader reboots this unit next.
        check_model_hardware.call_local(*model)

    # Read the file: this process's config was loaded before the leader's copy arrived.
    shared_config = ConfigParserMod(strict=False)
    shared_config.read(resolve_global_config_path())
    leader_address = shared_config.get("cluster.topology", "leader_address")

    clear_previous_leader_overrides(resolve_local_config_path())
    point_clock_at_leader(leader_address, leader_time)

    assigned = get_local_model()
    if assigned is not None and not report_model_to_leader(leader_address, *assigned):
        raise RuntimeError(f"Unable to report this unit's model to the leader at {leader_address}.")
    return assigned
