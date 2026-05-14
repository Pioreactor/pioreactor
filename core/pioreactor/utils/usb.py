# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import msgspec


USB_MOUNT_ROOT = Path(os.environ.get("PIOREACTOR_USB_MOUNT_ROOT", "/run/pioreactor/usb"))
SUPPORTED_FILESYSTEMS = {"exfat", "vfat", "ext4"}
UPDATE_ARCHIVE_PATTERN = re.compile(r"^release_(?P<version>\d{2}\.\d{1,2}\.\d+\w{0,6})\.zip$")


class UsbPartition(msgspec.Struct, frozen=True):
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
        payload = msgspec.structs.asdict(self)
        payload["mounted"] = self.is_mounted
        payload["display_name"] = self.display_name
        payload["pioreactor_mountpoint"] = str(self.pioreactor_mountpoint)
        return payload


class UsbUpdateArchive(msgspec.Struct, frozen=True):
    path: Path
    version: str

    def as_dict(self) -> dict[str, str]:
        return {"path": str(self.path), "version": self.version}


class UsbPluginWheel(msgspec.Struct, frozen=True):
    path: Path
    name: str
    version: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {"path": str(self.path), "name": self.name, "version": self.version}


class UsbScan(msgspec.Struct, frozen=True):
    mountpoint: Path
    updates: tuple[UsbUpdateArchive, ...]
    plugins: tuple[UsbPluginWheel, ...]
    writable: bool
    free_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "mountpoint": str(self.mountpoint),
            "updates": [update.as_dict() for update in self.updates],
            "plugins": [plugin.as_dict() for plugin in self.plugins],
            "writable": self.writable,
            "free_bytes": self.free_bytes,
        }


class UsbStatus(msgspec.Struct, frozen=True):
    status: str
    partitions: tuple[dict[str, Any], ...]
    active_mount: dict[str, Any] | None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "partitions": list(self.partitions),
            "active_mount": self.active_mount,
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


def get_fake_usb_status() -> UsbStatus:
    mounted = UsbPartition(
        device="/dev/sda1",
        parent_device="/dev/sda",
        label="PIOREACTOR",
        uuid="7A2B-91FE",
        fstype="exfat",
        size_bytes=31_000_000_000,
        mountpoints=("/run/pioreactor/usb/usb-7A2B-91FE",),
        removable=True,
    )
    detected = UsbPartition(
        device="/dev/sdb1",
        parent_device="/dev/sdb",
        label="LAB-EXPORTS",
        uuid="B8E1-4C91",
        fstype="vfat",
        size_bytes=15_500_000_000,
        mountpoints=(),
        removable=True,
    )
    active_mount = mounted.as_dict()
    active_mount["mountpoint"] = mounted.mountpoints[0]
    active_mount["writable"] = True
    active_mount["free_bytes"] = 24_000_000_000

    return UsbStatus(
        status="mounted",
        partitions=(
            _partition_status_as_dict(mounted),
            _partition_status_as_dict(detected),
        ),
        active_mount=active_mount,
    )


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
        if not _verify_writable(mountpoint):
            _remount_usb_partition(partition, mountpoint)
        if not _verify_writable(mountpoint):
            raise ValueError(f"{mountpoint} is not writable.")
        return mountpoint

    mountpoint = partition.pioreactor_mountpoint
    mountpoint.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "sudo",
            "mount",
            "-o",
            ",".join(_mount_options_for_partition(partition)),
            partition.device,
            str(mountpoint),
        ],
        check=True,
    )
    if not _verify_writable(mountpoint):
        raise ValueError(f"{mountpoint} is not writable.")
    return mountpoint


def eject_usb_partition(partition: UsbPartition) -> None:
    for mountpoint in partition.mountpoints:
        subprocess.run(["sync"], check=True)
        subprocess.run(["sudo", "umount", mountpoint], check=True)
        mountpoint_path = Path(mountpoint)
        if mountpoint_path.exists() and _is_relative_to(mountpoint_path, USB_MOUNT_ROOT):
            try:
                mountpoint_path.rmdir()
            except OSError:
                pass

    if partition.parent_device and shutil.which("udisksctl"):
        subprocess.run(["sudo", "udisksctl", "power-off", "-b", partition.parent_device], check=True)
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
    plugins = tuple(
        UsbPluginWheel(path=path, name=name, version=version)
        for path, name, version in _find_plugin_wheels(mountpoint)
    )
    usage = shutil.disk_usage(mountpoint)
    return UsbScan(
        mountpoint=mountpoint,
        updates=updates,
        plugins=plugins,
        writable=_verify_writable(mountpoint),
        free_bytes=usage.free,
    )


def get_usb_status() -> UsbStatus:
    try:
        partitions = discover_usb_partitions()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return UsbStatus(status="error", partitions=(), active_mount=None, error=str(exc))

    active_partitions = [
        partition
        for partition in partitions
        if any(_is_relative_to(Path(mountpoint), USB_MOUNT_ROOT) for mountpoint in partition.mountpoints)
    ]
    partition_payloads = tuple(_partition_status_as_dict(partition) for partition in partitions)
    active_mount = _default_active_mount_as_dict(active_partitions)

    if not partitions:
        return UsbStatus(status="absent", partitions=partition_payloads, active_mount=None)

    if len(active_partitions) > 1:
        return UsbStatus(status="multiple_present", partitions=partition_payloads, active_mount=active_mount)

    if len(active_partitions) == 1:
        active_mount = _active_mount_as_dict(active_partitions[0])
        status = "mounted"
        if active_mount.get("writable") is False:
            status = "mounted_readonly"
        return UsbStatus(status=status, partitions=partition_payloads, active_mount=active_mount)

    supported_partitions = [
        partition for partition in partitions if partition.fstype in SUPPORTED_FILESYSTEMS
    ]
    if len(partitions) > 1:
        return UsbStatus(status="multiple_present", partitions=partition_payloads, active_mount=None)
    if not supported_partitions:
        return UsbStatus(status="unsupported", partitions=partition_payloads, active_mount=None)
    return UsbStatus(status="present_unmounted", partitions=partition_payloads, active_mount=None)


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
        default_partition = _default_writable_partition(mounted)
        if default_partition is not None:
            return _pioreactor_managed_mountpoint(default_partition)
        names = ", ".join(partition.mountpoints[0] for partition in mounted)
        raise ValueError(
            f"Multiple Pioreactor-managed USB mounts found, but none are writable. Choose one with --mount: {names}"
        )
    return Path(mounted[0].mountpoints[0])


def resolve_usb_plugin_wheel(filepath: str) -> Path:
    path = Path(filepath)
    if path.suffix != ".whl":
        raise ValueError("USB plugin installs currently support .whl files only.")
    if not path.exists():
        raise ValueError(f"{filepath} does not exist.")

    resolved_path = path.resolve()
    for partition in find_mounted_pioreactor_usb_partitions():
        for mountpoint in partition.mountpoints:
            mountpoint_path = Path(mountpoint)
            if mountpoint_path.exists() and _is_relative_to(resolved_path, mountpoint_path.resolve()):
                return resolved_path

    raise ValueError(f"{filepath} is not on a Pioreactor-managed USB mount.")


def get_usb_export_directory() -> Path:
    mountpoint = choose_usb_mountpoint()
    export_dir = mountpoint / "pioreactor" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir


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


def _partition_status_as_dict(partition: UsbPartition) -> dict[str, Any]:
    payload = partition.as_dict()
    managed_mountpoints = _pioreactor_managed_mountpoints(partition)
    if managed_mountpoints:
        mountpoint = managed_mountpoints[0]
        payload["mountpoint"] = str(mountpoint)
        payload["writable"] = _verify_writable(mountpoint)
        try:
            payload["free_bytes"] = shutil.disk_usage(mountpoint).free
        except OSError:
            payload["free_bytes"] = None
    if partition.fstype not in SUPPORTED_FILESYSTEMS:
        supported = ", ".join(sorted(SUPPORTED_FILESYSTEMS))
        payload["unsupported_reason"] = (
            f"Unsupported filesystem {partition.fstype!r}. Supported: {supported}."
        )
    else:
        payload["unsupported_reason"] = None
    return payload


def _active_mount_as_dict(partition: UsbPartition) -> dict[str, Any]:
    mountpoint = _pioreactor_managed_mountpoint(partition)
    payload = partition.as_dict()
    payload["mountpoint"] = str(mountpoint)
    payload["writable"] = _verify_writable(mountpoint)
    payload["free_bytes"] = shutil.disk_usage(mountpoint).free
    return payload


def _default_active_mount_as_dict(partitions: list[UsbPartition]) -> dict[str, Any] | None:
    default_partition = _default_writable_partition(partitions)
    if default_partition is None:
        return None
    return _active_mount_as_dict(default_partition)


def _default_writable_partition(partitions: list[UsbPartition]) -> UsbPartition | None:
    for partition in sorted(partitions, key=lambda p: p.device):
        mountpoint = _pioreactor_managed_mountpoint(partition)
        if _verify_writable(mountpoint):
            return partition
    return None


def _pioreactor_managed_mountpoint(partition: UsbPartition) -> Path:
    mountpoints = _pioreactor_managed_mountpoints(partition)
    if not mountpoints:
        raise ValueError(f"{partition.device} is not mounted under {USB_MOUNT_ROOT}.")
    return mountpoints[0]


def _pioreactor_managed_mountpoints(partition: UsbPartition) -> list[Path]:
    return [
        mountpoint
        for mountpoint in (Path(raw_mountpoint) for raw_mountpoint in partition.mountpoints)
        if _is_relative_to(mountpoint, USB_MOUNT_ROOT)
    ]


def _find_plugin_wheels(mountpoint: Path) -> list[tuple[Path, str, str | None]]:
    candidates = [mountpoint, mountpoint / "pioreactor" / "plugins"]
    seen: set[Path] = set()
    plugins: list[tuple[Path, str, str | None]] = []

    for directory in candidates:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.whl")):
            if path in seen:
                continue
            seen.add(path)
            name, version = _parse_wheel_name(path.name)
            plugins.append((path, name, version))

    return plugins


def _parse_wheel_name(filename: str) -> tuple[str, str | None]:
    parts = filename.removesuffix(".whl").split("-")
    if len(parts) < 2:
        return filename.removesuffix(".whl").replace("_", "-"), None
    return parts[0].replace("_", "-"), parts[1]


def _as_bool(value: object) -> bool:
    return value is True or value == 1 or value == "1"


def _safe_path_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return cleaned or "usb"


def _normalize_device_path(value: str) -> str:
    return value if value.startswith("/dev/") else f"/dev/{value}"


def _mount_options_for_partition(partition: UsbPartition) -> list[str]:
    options = ["rw", "nosuid", "nodev", "noexec"]

    if partition.fstype in {"exfat", "vfat"}:
        options.extend([f"uid={os.getuid()}", f"gid={os.getgid()}", "umask=002"])

    return options


def _remount_usb_partition(partition: UsbPartition, mountpoint: Path) -> None:
    if partition.fstype not in {"exfat", "vfat"}:
        return

    subprocess.run(
        [
            "sudo",
            "mount",
            "-o",
            f"remount,{','.join(_mount_options_for_partition(partition))}",
            str(mountpoint),
        ],
        check=True,
    )


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
