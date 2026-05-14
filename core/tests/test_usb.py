# -*- coding: utf-8 -*-
import json
import subprocess
from pathlib import Path

from click.testing import CliRunner
from pioreactor.cli.pio import pio
from pioreactor.utils import usb as usb_utils


class DummyCompletedProcess:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def test_discover_usb_partitions_parses_removable_partition(monkeypatch) -> None:
    lsblk_payload = {
        "blockdevices": [
            {
                "name": "/dev/sda",
                "path": "/dev/sda",
                "type": "disk",
                "rm": True,
                "size": 1000,
                "children": [
                    {
                        "name": "/dev/sda1",
                        "path": "/dev/sda1",
                        "pkname": "/dev/sda",
                        "type": "part",
                        "rm": False,
                        "size": 900,
                        "fstype": "exfat",
                        "label": "PIOREACTOR",
                        "uuid": "7A2B-91FE",
                        "mountpoints": [],
                    }
                ],
            },
            {
                "name": "/dev/mmcblk0",
                "path": "/dev/mmcblk0",
                "type": "disk",
                "rm": False,
                "size": 1000,
                "children": [],
            },
        ]
    }

    def fake_run(command: list[str], **kwargs) -> DummyCompletedProcess:
        assert command[0] == "lsblk"
        return DummyCompletedProcess(json.dumps(lsblk_payload))

    monkeypatch.setattr(subprocess, "run", fake_run)

    partitions = usb_utils.discover_usb_partitions()

    assert len(partitions) == 1
    partition = partitions[0]
    assert partition.device == "/dev/sda1"
    assert partition.parent_device == "/dev/sda"
    assert partition.display_name == "PIOREACTOR"
    assert partition.pioreactor_mountpoint == usb_utils.USB_MOUNT_ROOT / "usb-7A2B-91FE"


def test_scan_usb_mount_detects_release_archives(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    mountpoint = mount_root / "usb-7A2B-91FE"
    mountpoint.mkdir(parents=True)
    (mountpoint / "release_25.6.0.zip").write_text("release", encoding="utf-8")
    (mountpoint / "release-25.6.0.zip").write_text("ignore", encoding="utf-8")
    (mountpoint / "notes.txt").write_text("ignore", encoding="utf-8")
    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)

    scan = usb_utils.scan_usb_mount(mountpoint)

    assert scan.writable is True
    assert [update.path.name for update in scan.updates] == ["release_25.6.0.zip"]
    assert scan.updates[0].version == "25.6.0"


def test_scan_usb_mount_detects_plugin_wheels(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    mountpoint = mount_root / "usb-7A2B-91FE"
    plugins_dir = mountpoint / "pioreactor" / "plugins"
    plugins_dir.mkdir(parents=True)
    (mountpoint / "pioreactor_demo-1.2.3-py3-none-any.whl").write_text("wheel", encoding="utf-8")
    (plugins_dir / "pioreactor_other-2.0.0-py3-none-any.whl").write_text("wheel", encoding="utf-8")
    (plugins_dir / "plugin.py").write_text("ignore", encoding="utf-8")
    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)

    scan = usb_utils.scan_usb_mount(mountpoint)

    assert [plugin.name for plugin in scan.plugins] == ["pioreactor-demo", "pioreactor-other"]
    assert [plugin.version for plugin in scan.plugins] == ["1.2.3", "2.0.0"]


def test_get_usb_status_reports_present_unmounted(monkeypatch) -> None:
    partition = usb_utils.UsbPartition(
        device="/dev/sda1",
        parent_device="/dev/sda",
        label="PIOREACTOR",
        uuid="7A2B-91FE",
        fstype="exfat",
        size_bytes=1000,
        mountpoints=(),
        removable=True,
    )

    monkeypatch.setattr(usb_utils, "discover_usb_partitions", lambda: [partition])

    status = usb_utils.get_usb_status()

    assert status.status == "present_unmounted"
    assert status.active_mount is None
    assert status.partitions[0]["unsupported_reason"] is None


def test_get_usb_status_selects_first_device_path_writable_managed_usb_when_multiple_are_mounted(
    tmp_path: Path, monkeypatch
) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    z_mountpoint = mount_root / "usb-z"
    a_mountpoint = mount_root / "usb-a"
    z_mountpoint.mkdir(parents=True)
    a_mountpoint.mkdir(parents=True)
    partitions = [
        usb_utils.UsbPartition(
            device="/dev/sdb1",
            parent_device="/dev/sdb",
            label="Z_DRIVE",
            uuid="Z",
            fstype="exfat",
            size_bytes=2000,
            mountpoints=(z_mountpoint.as_posix(),),
            removable=True,
        ),
        usb_utils.UsbPartition(
            device="/dev/sda1",
            parent_device="/dev/sda",
            label="A_DRIVE",
            uuid="A",
            fstype="vfat",
            size_bytes=1000,
            mountpoints=(a_mountpoint.as_posix(),),
            removable=True,
        ),
    ]

    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)
    monkeypatch.setattr(usb_utils, "discover_usb_partitions", lambda: partitions)

    status = usb_utils.get_usb_status()

    assert status.status == "multiple_present"
    assert status.active_mount is not None
    assert status.active_mount["display_name"] == "A_DRIVE"
    assert status.active_mount["mountpoint"] == a_mountpoint.as_posix()
    assert status.active_mount["writable"] is True
    assert [partition["writable"] for partition in status.partitions] == [True, True]


def test_choose_usb_mountpoint_selects_first_device_path_writable_managed_usb_when_multiple_are_mounted(
    tmp_path: Path, monkeypatch
) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    b_mountpoint = mount_root / "usb-b"
    a_mountpoint = mount_root / "usb-a"
    b_mountpoint.mkdir(parents=True)
    a_mountpoint.mkdir(parents=True)
    partitions = [
        usb_utils.UsbPartition(
            device="/dev/sdb1",
            parent_device="/dev/sdb",
            label="B_DRIVE",
            uuid="B",
            fstype="exfat",
            size_bytes=2000,
            mountpoints=(b_mountpoint.as_posix(),),
            removable=True,
        ),
        usb_utils.UsbPartition(
            device="/dev/sda1",
            parent_device="/dev/sda",
            label="A_DRIVE",
            uuid="A",
            fstype="vfat",
            size_bytes=1000,
            mountpoints=(a_mountpoint.as_posix(),),
            removable=True,
        ),
    ]

    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)
    monkeypatch.setattr(usb_utils, "discover_usb_partitions", lambda: partitions)

    assert usb_utils.choose_usb_mountpoint() == a_mountpoint


def test_verify_writable_uses_mount_read_write_options(tmp_path: Path, monkeypatch) -> None:
    mountpoint = tmp_path / "run" / "pioreactor" / "usb" / "usb-a"
    mountpoint.mkdir(parents=True)
    mountinfo = (
        f"1 0 8:1 / {tmp_path.as_posix()} rw,relatime - ext4 /dev/root rw\n"
        f"2 1 8:2 / {mountpoint.as_posix()} ro,nosuid,nodev - vfat /dev/sda1 rw\n"
    )

    monkeypatch.setattr(Path, "read_text", lambda _path, encoding=None: mountinfo)

    assert usb_utils._verify_writable(mountpoint) is False


def test_resolve_usb_plugin_wheel_rejects_paths_outside_usb_mount(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    mountpoint = mount_root / "usb-7A2B-91FE"
    mountpoint.mkdir(parents=True)
    outside_wheel = tmp_path / "pioreactor_demo-1.2.3-py3-none-any.whl"
    outside_wheel.write_text("wheel", encoding="utf-8")
    partition = usb_utils.UsbPartition(
        device="/dev/sda1",
        parent_device="/dev/sda",
        label="PIOREACTOR",
        uuid="7A2B-91FE",
        fstype="exfat",
        size_bytes=1000,
        mountpoints=(mountpoint.as_posix(),),
        removable=True,
    )

    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)
    monkeypatch.setattr(usb_utils, "discover_usb_partitions", lambda: [partition])

    try:
        usb_utils.resolve_usb_plugin_wheel(outside_wheel.as_posix())
    except ValueError as exc:
        assert "not on a Pioreactor-managed USB mount" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_resolve_usb_plugin_wheel_accepts_wheels_on_usb_mount(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    mountpoint = mount_root / "usb-7A2B-91FE"
    mountpoint.mkdir(parents=True)
    wheel = mountpoint / "pioreactor_demo-1.2.3-py3-none-any.whl"
    wheel.write_text("wheel", encoding="utf-8")
    partition = usb_utils.UsbPartition(
        device="/dev/sda1",
        parent_device="/dev/sda",
        label="PIOREACTOR",
        uuid="7A2B-91FE",
        fstype="exfat",
        size_bytes=1000,
        mountpoints=(mountpoint.as_posix(),),
        removable=True,
    )

    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)
    monkeypatch.setattr(usb_utils, "discover_usb_partitions", lambda: [partition])

    assert usb_utils.resolve_usb_plugin_wheel(wheel.as_posix()) == wheel.resolve()


def test_mount_usb_partition_uses_user_writable_options_for_vfat(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    commands: list[list[str]] = []
    partition = usb_utils.UsbPartition(
        device="/dev/sda1",
        parent_device="/dev/sda",
        label="PRUSA3D",
        uuid="1C2C-7EA6",
        fstype="vfat",
        size_bytes=1000,
        mountpoints=(),
        removable=True,
    )

    def fake_run(command: list[str], **kwargs) -> DummyCompletedProcess:
        commands.append(command)
        return DummyCompletedProcess()

    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)
    monkeypatch.setattr(usb_utils.os, "getuid", lambda: 1000)
    monkeypatch.setattr(usb_utils.os, "getgid", lambda: 1001)
    monkeypatch.setattr(subprocess, "run", fake_run)

    mountpoint = usb_utils.mount_usb_partition(partition)

    assert mountpoint == mount_root / "usb-1C2C-7EA6"
    assert commands == [
        [
            "sudo",
            "mount",
            "-o",
            "rw,nosuid,nodev,noexec,uid=1000,gid=1001,umask=002",
            "/dev/sda1",
            str(mountpoint),
        ]
    ]


def test_eject_usb_partition_runs_udisksctl_through_sudo(monkeypatch) -> None:
    commands: list[list[str]] = []
    partition = usb_utils.UsbPartition(
        device="/dev/sda1",
        parent_device="/dev/sda",
        label="PRUSA3D",
        uuid="1C2C-7EA6",
        fstype="vfat",
        size_bytes=1000,
        mountpoints=("/run/pioreactor/usb/usb-1C2C-7EA6",),
        removable=True,
    )

    def fake_run(command: list[str], **kwargs) -> DummyCompletedProcess:
        commands.append(command)
        return DummyCompletedProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        usb_utils.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "udisksctl" else None
    )

    usb_utils.eject_usb_partition(partition)

    assert commands == [
        ["sync"],
        ["sudo", "umount", "/run/pioreactor/usb/usb-1C2C-7EA6"],
        ["sudo", "udisksctl", "power-off", "-b", "/dev/sda"],
    ]


def test_pio_usb_scan_prints_update_artifacts(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    mountpoint = mount_root / "usb-7A2B-91FE"
    mountpoint.mkdir(parents=True)
    (mountpoint / "release_25.6.0.zip").write_text("release", encoding="utf-8")
    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)

    runner = CliRunner()
    result = runner.invoke(pio, ["usb", "scan", "--mount", str(mountpoint)])

    assert result.exit_code == 0
    assert "Writable: yes" in result.output
    assert "release_25.6.0.zip (25.6.0)" in result.output
    assert f"source: {mountpoint / 'release_25.6.0.zip'}" in result.output


def test_pio_usb_path_prints_selected_mount_path(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    mountpoint = mount_root / "usb-7A2B-91FE"
    mountpoint.mkdir(parents=True)

    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)

    runner = CliRunner()
    result = runner.invoke(pio, ["usb", "path", "--mount", str(mountpoint)])

    assert result.exit_code == 0
    assert result.output == f"{mountpoint}\n"
