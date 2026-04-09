#!/opt/pioreactor/venv/bin/python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import shutil
import sys
from importlib.metadata import distribution as load_distribution
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Mapping
from typing import Sequence


DESTINATION_ROOT = Path("/home/pioreactor/.pioreactor/plugins/ui")
ENTRY_POINT_SOURCE = "entry_points"
YAML_SUFFIXES = {".yaml", ".yml"}

PluginSnapshots = Mapping[str, Mapping[str, str]]
DistributionGetter = Callable[[str], Any]
CopyRemoteFile = Callable[[str, str, str], None]


def _is_descriptor_relative_path(relative_path: PurePosixPath) -> bool:
    if relative_path.suffix not in YAML_SUFFIXES:
        return False

    parts = relative_path.parts
    if len(parts) < 3 or parts[0] != "ui":
        return False

    if parts[1] == "jobs":
        return True

    if parts[1] == "automations":
        return True

    return False


def _destination_for_relative_path(relative_path: PurePosixPath, destination_root: Path) -> Path:
    return destination_root.joinpath(*relative_path.parts[1:])


def collect_descriptor_mappings_from_distribution(
    distribution_obj: Any,
    *,
    destination_root: Path = DESTINATION_ROOT,
) -> list[tuple[Path, Path]]:
    mappings: list[tuple[Path, Path]] = []
    distribution_files = distribution_obj.files or []

    for relative_path in sorted((PurePosixPath(str(path)) for path in distribution_files), key=str):
        if not _is_descriptor_relative_path(relative_path):
            continue

        source = Path(distribution_obj.locate_file(relative_path.as_posix()))
        if not source.exists():
            raise FileNotFoundError(
                f"Descriptor file {relative_path.as_posix()} is missing from distribution."
            )

        destination = _destination_for_relative_path(relative_path, destination_root)
        mappings.append((source, destination))

    return mappings


def copy_descriptor_file_if_needed(source: Path, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and destination.read_bytes() == source.read_bytes():
        return False

    shutil.copy2(source, destination)
    return True


def _is_packaged_plugin(plugin_snapshot: Mapping[str, str]) -> bool:
    return plugin_snapshot.get("source") == ENTRY_POINT_SOURCE


def load_local_plugin_snapshots() -> dict[str, dict[str, str]]:
    from pioreactor.cli import run as _run  # noqa: F401
    from pioreactor.plugin_management import get_plugins

    plugins = get_plugins()
    return {
        plugin_name: {
            "version": plugin.version,
            "source": plugin.source,
        }
        for plugin_name, plugin in plugins.items()
    }


def repair_local_descriptors(
    plugin_snapshots: PluginSnapshots,
    *,
    dist_getter: DistributionGetter = load_distribution,
    destination_root: Path = DESTINATION_ROOT,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "mode": "repair-local",
        "copied_by_plugin": {},
        "skipped_plugins": {},
        "errors": {},
    }

    for plugin_name in sorted(plugin_snapshots, key=str.casefold):
        plugin_snapshot = plugin_snapshots[plugin_name]

        if not _is_packaged_plugin(plugin_snapshot):
            report["skipped_plugins"][plugin_name] = "non_packaged_plugin"
            continue

        try:
            descriptor_mappings = collect_descriptor_mappings_from_distribution(
                dist_getter(plugin_name),
                destination_root=destination_root,
            )
            if not descriptor_mappings:
                report["skipped_plugins"][plugin_name] = "no_descriptor_assets"
                continue

            copied_files: list[str] = []
            for source, destination in descriptor_mappings:
                if copy_descriptor_file_if_needed(source, destination):
                    copied_files.append(str(destination))

            report["copied_by_plugin"][plugin_name] = copied_files
        except PackageNotFoundError as exc:
            report["errors"][plugin_name] = str(exc)
        except Exception as exc:
            report["errors"][plugin_name] = f"{type(exc).__name__}: {exc}"

    report["copied_files_count"] = sum(len(paths) for paths in report["copied_by_plugin"].values())
    return report


def load_remote_plugin_snapshots(
    units: Sequence[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    from pioreactor.pubsub import get_from
    from pioreactor.utils.networking import resolve_to_address

    snapshots_by_unit: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    for unit in units:
        try:
            response = get_from(resolve_to_address(unit), "/unit_api/plugins/installed", timeout=10)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise TypeError("Worker plugin payload is not a list.")
            snapshots_by_unit[unit] = payload
        except Exception as exc:
            errors[unit] = f"{type(exc).__name__}: {exc}"

    return snapshots_by_unit, errors


def _remote_packaged_plugin_versions(plugin_snapshots: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for plugin_snapshot in plugin_snapshots:
        plugin_name = plugin_snapshot.get("name")
        plugin_version = plugin_snapshot.get("version")
        plugin_source = plugin_snapshot.get("source")

        if (
            isinstance(plugin_name, str)
            and isinstance(plugin_version, str)
            and plugin_source == ENTRY_POINT_SOURCE
        ):
            versions[plugin_name] = plugin_version

    return versions


def sync_descriptors_to_workers(
    local_plugin_snapshots: PluginSnapshots,
    remote_snapshots_by_unit: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    dist_getter: DistributionGetter = load_distribution,
    destination_root: Path = DESTINATION_ROOT,
    copy_remote_file: CopyRemoteFile,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "mode": "sync-from-leader",
        "copied_by_unit": {},
        "errors": {},
        "skipped_units": {},
    }

    for unit in sorted(remote_snapshots_by_unit):
        remote_versions = _remote_packaged_plugin_versions(remote_snapshots_by_unit[unit])
        copied_paths: list[str] = []

        for plugin_name in sorted(local_plugin_snapshots, key=str.casefold):
            plugin_snapshot = local_plugin_snapshots[plugin_name]
            if not _is_packaged_plugin(plugin_snapshot):
                continue

            local_version = plugin_snapshot.get("version")
            if remote_versions.get(plugin_name) != local_version:
                continue

            try:
                descriptor_mappings = collect_descriptor_mappings_from_distribution(
                    dist_getter(plugin_name),
                    destination_root=destination_root,
                )
                if not descriptor_mappings:
                    continue

                for source, destination in descriptor_mappings:
                    copy_descriptor_file_if_needed(source, destination)
                    copy_remote_file(unit, str(destination), str(destination))
                    copied_paths.append(str(destination))
            except PackageNotFoundError as exc:
                report["errors"][f"{unit}:{plugin_name}"] = str(exc)
            except Exception as exc:
                report["errors"][f"{unit}:{plugin_name}"] = f"{type(exc).__name__}: {exc}"

        if copied_paths:
            report["copied_by_unit"][unit] = copied_paths
        else:
            report["skipped_units"][unit] = "no_matching_packaged_plugins"

    report["copied_files_count"] = sum(len(paths) for paths in report["copied_by_unit"].values())
    return report


def run_sync_from_leader() -> dict[str, Any]:
    from pioreactor.cluster_management import get_active_workers_in_inventory
    from pioreactor.config import get_leader_hostname
    from pioreactor.utils.networking import cp_file_across_cluster
    from pioreactor.whoami import get_unit_name

    if get_unit_name() != get_leader_hostname():
        return {
            "mode": "sync-from-leader",
            "copied_by_unit": {},
            "errors": {},
            "skipped_units": {"self": "not_leader"},
            "copied_files_count": 0,
        }

    local_plugin_snapshots = load_local_plugin_snapshots()
    units = list(get_active_workers_in_inventory())
    if not units:
        return {
            "mode": "sync-from-leader",
            "copied_by_unit": {},
            "errors": {},
            "skipped_units": {"cluster": "no_active_workers"},
            "copied_files_count": 0,
        }

    remote_snapshots_by_unit, fetch_errors = load_remote_plugin_snapshots(units)
    report = sync_descriptors_to_workers(
        local_plugin_snapshots,
        remote_snapshots_by_unit,
        copy_remote_file=cp_file_across_cluster,
    )
    report["errors"].update({f"{unit}:fetch": error for unit, error in fetch_errors.items()})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair Pioreactor plugin descriptor assets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("repair-local")
    subparsers.add_parser("sync-from-leader")

    args = parser.parse_args()

    if args.command == "repair-local":
        report = repair_local_descriptors(load_local_plugin_snapshots())
    elif args.command == "sync-from-leader":
        report = run_sync_from_leader()
    else:
        raise ValueError(f"Unsupported command {args.command}")

    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
