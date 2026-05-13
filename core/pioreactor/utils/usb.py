# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


USB_MOUNT_ROOT = Path(os.environ.get("PIOREACTOR_USB_MOUNT_ROOT", "/run/pioreactor/usb"))
SUPPORTED_FILESYSTEMS = {"exfat", "vfat", "ext4"}
UPDATE_ARCHIVE_PATTERN = re.compile(r"^release_(?P<version>\d{2}\.\d{1,2}\.\d+\w{0,6})\.zip$")


@dataclass(frozen=True)
class UsbPartition:
    device: str
    parent_device: str | None
    label: str | None
    uuid: str | None
    fstype: str | None
    size_bytes: int | None
    mountpoints: tuple[str, ...]
    removable: bool

    @property
    def is_mounted(self) -> bool:
        return len(self.mountpoints) > 0

    @property
    def display_name(self) -> str:
        return self.label or self.uuid or Path(self.device).name

    @property
    def mount_id(self) -> str:
        if self.uuid:
            return f"usb-{_safe_path_component(self.uuid)}"
        if self.label:
            return f"{_safe_path_component(self.label)}-{Path(self.device).name}"
        return Path(self.device).name

    @property
    def pioreactor_mountpoint(self) -> Path:
        return USB_MOUNT_ROOT / self.mount_id

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mounted"] = self.is_mounted
        payload["display_name"] = self.display_name
        payload["pioreactor_mountpoint"] = str(self.pioreactor_mountpoint)
        return payload


@dataclass(frozen=True)
class UsbUpdateArchive:
    path: Path
    version: str

    def as_dict(self) -> dict[str, str]:
        return {"path": str(self.path), "version": self.version}


@dataclass(frozen=True)
class UsbScan:
    mountpoint: Path
    updates: tuple[UsbUpdateArchive, ...]
    writable: bool
    free_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "mountpoint": str(self.mountpoint),
            "updates": [update.as_dict() for update in self.updates],
            "writable": self.writable,
            "free_bytes": self.free_bytes,
        }


def discover_usb_partitions() -> list[UsbPartition]:
    result = subprocess.run(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--fs",
            "--paths",
            "--output",
            "NAME,PATH,PKNAME,TYPE,RM,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(result.stdout)
    partitions: list[UsbPartition] = []

    for device in payload.get("blockdevices", []):
        partitions.extend(_parse_lsblk_node(device, parent_device=None, parent_removable=False))

    return partitions


def mount_usb_partition(partition: UsbPartition) -> Path:
    if not partition.removable:
        raise ValueError(f"{partition.device} is not a removable device.")
    if partition.fstype not in SUPPORTED_FILESYSTEMS:
        supported = ", ".join(sorted(SUPPORTED_FILESYSTEMS))
        raise ValueError(
            f"{partition.device} has unsupported filesystem {partition.fstype!r}. Supported: {supported}."
        )
    if partition.is_mounted:
        mountpoint = Path(partition.mountpoints[0])
        if not _is_relative_to(mountpoint, USB_MOUNT_ROOT):
            raise ValueError(f"{partition.device} is already mounted outside {USB_MOUNT_ROOT}: {mountpoint}")
        return mountpoint

    mountpoint = partition.pioreactor_mountpoint
    mountpoint.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["sudo", "mount", "-o", "rw,nosuid,nodev,noexec", partition.device, str(mountpoint)],
        check=True,
    )
    if not _verify_writable(mountpoint):
        raise ValueError(f"{mountpoint} is not writable.")
    return mountpoint


def eject_usb_partition(partition: UsbPartition) -> None:
    for mountpoint in partition.mountpoints:
        subprocess.run(["sync"], check=True)
        subprocess.run(["sudo", "umount", mountpoint], check=True)

    if partition.parent_device and shutil.which("udisksctl"):
        subprocess.run(["udisksctl", "power-off", "-b", partition.parent_device], check=True)
    elif partition.parent_device and shutil.which("eject"):
        subprocess.run(["sudo", "eject", partition.parent_device], check=True)


def scan_usb_mount(mountpoint: Path) -> UsbScan:
    _assert_mount_is_under_usb_root(mountpoint)
    updates = tuple(
        sorted(
            (
                UsbUpdateArchive(path=path, version=match.group("version"))
                for path in mountpoint.iterdir()
                if path.is_file() and (match := UPDATE_ARCHIVE_PATTERN.fullmatch(path.name))
            ),
            key=lambda update: update.path.name,
        )
    )
    usage = shutil.disk_usage(mountpoint)
    return UsbScan(
        mountpoint=mountpoint,
        updates=updates,
        writable=_verify_writable(mountpoint),
        free_bytes=usage.free,
    )


def find_mounted_pioreactor_usb_partitions() -> list[UsbPartition]:
    return [
        partition
        for partition in discover_usb_partitions()
        if any(_is_relative_to(Path(mountpoint), USB_MOUNT_ROOT) for mountpoint in partition.mountpoints)
    ]


def choose_usb_partition(device: str | None = None, require_mounted: bool = False) -> UsbPartition:
    partitions = discover_usb_partitions()
    requested_device = _normalize_device_path(device) if device is not None else None
    candidates = [
        partition
        for partition in partitions
        if partition.removable and (requested_device is None or partition.device == requested_device)
    ]
    if require_mounted:
        candidates = [partition for partition in candidates if partition.is_mounted]

    if not candidates:
        if device:
            raise ValueError(f"No removable USB partition found at {device}.")
        raise ValueError("No removable USB partition found.")
    if len(candidates) > 1:
        devices = ", ".join(partition.device for partition in candidates)
        raise ValueError(f"Multiple USB partitions found. Choose one with --device: {devices}")
    return candidates[0]


def choose_usb_mountpoint(mountpoint: str | None = None) -> Path:
    if mountpoint is not None:
        path = Path(mountpoint).resolve()
        _assert_mount_is_under_usb_root(path)
        return path

    mounted = find_mounted_pioreactor_usb_partitions()
    if not mounted:
        raise ValueError("No Pioreactor-managed USB mount found. Run `pio usb mount` first.")
    if len(mounted) > 1:
        names = ", ".join(partition.mountpoints[0] for partition in mounted)
        raise ValueError(f"Multiple Pioreactor-managed USB mounts found. Choose one with --mount: {names}")
    return Path(mounted[0].mountpoints[0])


def build_usb_database_backup_path(mountpoint: Path, unit: str) -> Path:
    return mountpoint / "pioreactor" / "backups" / unit / "pioreactor.sqlite.backup"


def _parse_lsblk_node(
    node: dict[str, Any], parent_device: str | None, parent_removable: bool
) -> list[UsbPartition]:
    device_type = node.get("type")
    device = _normalize_device_path(str(node.get("path") or node.get("name")))
    removable = _as_bool(node.get("rm")) or parent_removable
    parent = (
        _normalize_device_path(str(node.get("pkname") or parent_device))
        if node.get("pkname") or parent_device
        else None
    )
    partitions: list[UsbPartition] = []

    children = node.get("children") or []
    if (device_type == "part" or (device_type == "disk" and not children)) and removable:
        partitions.append(
            UsbPartition(
                device=device,
                parent_device=parent,
                label=node.get("label"),
                uuid=node.get("uuid"),
                fstype=node.get("fstype"),
                size_bytes=int(node["size"]) if node.get("size") is not None else None,
                mountpoints=_normalize_mountpoints(node.get("mountpoints")),
                removable=removable,
            )
        )

    for child in children:
        partitions.extend(_parse_lsblk_node(child, parent_device=device, parent_removable=removable))

    return partitions


def _normalize_mountpoints(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, list):
        return tuple(str(item) for item in value if item)
    return ()


def _as_bool(value: object) -> bool:
    return value is True or value == 1 or value == "1"


def _safe_path_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return cleaned or "usb"


def _normalize_device_path(value: str) -> str:
    return value if value.startswith("/dev/") else f"/dev/{value}"


def _verify_writable(mountpoint: Path) -> bool:
    probe = mountpoint / ".pioreactor-usb-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _assert_mount_is_under_usb_root(mountpoint: Path) -> None:
    if not _is_relative_to(mountpoint.resolve(), USB_MOUNT_ROOT.resolve()):
        raise ValueError(f"{mountpoint} is not under {USB_MOUNT_ROOT}.")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
