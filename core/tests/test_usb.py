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


def test_pio_usb_backup_db_writes_to_usb_backup_path(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    mountpoint = mount_root / "usb-7A2B-91FE"
    mountpoint.mkdir(parents=True)
    calls: list[tuple[str, bool, int]] = []

    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)
    monkeypatch.setattr("pioreactor.cli.usb.get_unit_name", lambda: "pio-abc")

    def fake_backup_database(output: str, force: bool, backup_to_workers: int) -> None:
        calls.append((output, force, backup_to_workers))

    monkeypatch.setattr("pioreactor.cli.usb.backup_database", fake_backup_database)

    runner = CliRunner()
    result = runner.invoke(pio, ["usb", "backup-db", "--mount", str(mountpoint), "--force"])

    assert result.exit_code == 0
    assert calls == [
        (
            str(mountpoint / "pioreactor" / "backups" / "pio-abc" / "pioreactor.sqlite.backup"),
            True,
            0,
        )
    ]


def test_pio_usb_update_app_uses_single_scanned_release(tmp_path: Path, monkeypatch) -> None:
    mount_root = tmp_path / "run" / "pioreactor" / "usb"
    mountpoint = mount_root / "usb-7A2B-91FE"
    mountpoint.mkdir(parents=True)
    release = mountpoint / "release_25.6.0.zip"
    release.write_text("release", encoding="utf-8")
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(usb_utils, "USB_MOUNT_ROOT", mount_root)

    def fake_update_app(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr("pioreactor.cli.pio.update_app.callback", fake_update_app)

    runner = CliRunner()
    result = runner.invoke(pio, ["usb", "update", "app", "--mount", str(mountpoint), "--yes"])

    assert result.exit_code == 0
    assert calls == [
        {
            "branch": None,
            "sha": None,
            "no_deps": False,
            "repo": "pioreactor/pioreactor",
            "source": str(release),
            "version": None,
            "defer_web_restart": False,
        }
    ]
