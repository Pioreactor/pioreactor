# -*- coding: utf-8 -*-
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from msgspec.yaml import encode as yaml_encode
from pioreactor.boot_files import import_files
from pioreactor.models import PIOREACTOR_40ml__v1_5


PROFILE = b'version: "1.0"\nexperiment_profile_name: boot profile\n'
OWNER = (os.getuid(), os.getgid())


def stage(boot: Path, relative: str, content: bytes) -> Path:
    file = boot / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)
    return file


def test_import_replaces_assets_and_preserves_hardware_paths(tmp_path: Path) -> None:
    boot, data = tmp_path / "boot", tmp_path / "data"
    data.mkdir()
    sources = {
        "experiment_profiles/example.yml": PROFILE,
        "models/example.yaml": yaml_encode(PIOREACTOR_40ml__v1_5),
        "hardware/models/custom/1.0/adc.yaml": b"pd1: {driver: pico, address: 44, channel: 0}\n",
    }
    for relative, content in sources.items():
        stage(boot, relative, content)
        stage(data, relative, b"old content")

    assert import_files(boot, data, True, OWNER) == 0
    for relative, content in sources.items():
        destination = data / relative
        assert destination.read_bytes() == content
        assert destination.stat().st_mode & 0o777 == 0o664
        assert (destination.stat().st_uid, destination.stat().st_gid) == OWNER
        assert not (boot / relative).exists()
    assert import_files(boot, data, True, OWNER) == 0
    assert not list(data.rglob("*.bak"))


@pytest.mark.parametrize(
    "relative,content",
    [
        ("experiment_profiles/bad.yaml", b"version: 1.0\nexperiment_profile_name: bad\n"),
        (
            "experiment_profiles/bad.yaml",
            PROFILE
            + b"common:\n  jobs:\n    stirring:\n      actions:\n        - type: start\n          t: -1\n",
        ),
        ("models/bad.yaml", b"model_name: missing fields\n"),
        ("hardware/hats/1.2/pwm.yaml", b"[not, a, mapping]\n"),
        ("hardware/hats/1.2/pwm.yaml", b"invalid: [\n"),
    ],
)
def test_invalid_assets_preserve_existing_files_and_write_diagnostics(
    tmp_path: Path, relative: str, content: bytes
) -> None:
    boot, data = tmp_path / "boot", tmp_path / "data"
    source = stage(boot, relative, content)
    destination = stage(data, relative, b"original")
    good = stage(boot, "hardware/hats/1.2/gpio.yaml", b"pcb_led_pin: 17\n")
    assert import_files(boot, data, True, OWNER) == 1
    assert source.read_bytes() == content
    assert destination.read_bytes() == b"original"
    assert source.with_name(source.name + ".log").read_text().startswith("Failed to import")
    assert not good.exists()


def test_worker_imports_local_assets_and_leaves_profiles_and_unsupported_files(tmp_path: Path) -> None:
    boot, data = tmp_path / "boot", tmp_path / "data"
    data.mkdir()
    untouched = [
        stage(boot, "experiment_profiles/example.yaml", PROFILE),
        stage(boot, "plugins/example.whl", b"wheel"),
        stage(boot, "models/nested/example.yaml", b"not a top-level model"),
        stage(boot, "hardware/readme.txt", b"text"),
        stage(boot, "config.ini", b"config"),
    ]
    stage(boot, "models/example.yaml", yaml_encode(PIOREACTOR_40ml__v1_5))
    assert import_files(boot, data, False, OWNER) == 0
    assert (data / "models/example.yaml").exists()
    assert all(file.exists() for file in untouched)
    assert not (data / "experiment_profiles").exists()


def test_publish_failure_keeps_input_and_existing_destination(tmp_path: Path) -> None:
    boot, data = tmp_path / "boot", tmp_path / "data"
    source = stage(boot, "experiment_profiles/example.yaml", PROFILE)
    destination = stage(data, "experiment_profiles/example.yaml", b"original")
    with patch.object(Path, "replace", side_effect=OSError("disk failure")):
        assert import_files(boot, data, True, OWNER) == 1
    assert source.exists()
    assert destination.read_bytes() == b"original"
    assert not list(data.rglob(".bootfs-*"))


def test_destination_symlink_directory_is_not_followed(tmp_path: Path) -> None:
    boot, data, outside = tmp_path / "boot", tmp_path / "data", tmp_path / "outside"
    data.mkdir()
    outside.mkdir()
    (data / "hardware").symlink_to(outside, target_is_directory=True)
    source = stage(boot, "hardware/hats/1.2/pwm.yaml", b"controller: rpi_gpio\n")
    assert import_files(boot, data, True, OWNER) == 1
    assert source.exists()
    assert not list(outside.iterdir())


def test_corrected_file_is_retried_and_old_diagnostic_removed(tmp_path: Path) -> None:
    boot, data = tmp_path / "boot", tmp_path / "data"
    data.mkdir()
    source = stage(boot, "models/example.yaml", b"bad: model\n")
    assert import_files(boot, data, True, OWNER) == 1
    diagnostic = source.with_name(source.name + ".log")
    assert diagnostic.exists()
    source.write_bytes(yaml_encode(PIOREACTOR_40ml__v1_5))
    assert import_files(boot, data, True, OWNER) == 0
    assert not source.exists()
    assert not diagnostic.exists()


@pytest.mark.parametrize("configured,leader", [(False, True), (True, True), (True, False)])
def test_boot_wrapper_defers_unconfigured_units_and_passes_role(
    tmp_path: Path, configured: bool, leader: bool
) -> None:
    repo = Path(__file__).parents[2]
    data = tmp_path / "data"
    data.mkdir()
    if configured:
        (data / "config.ini").touch()
    env_file = tmp_path / "pioreactor.env"
    env_file.write_text(f'DOT_PIOREACTOR="{data}"\nPIO_VENV="{tmp_path}"\n')
    executable_dir = tmp_path / "bin"
    executable_dir.mkdir()
    record = tmp_path / "invocation"
    for name, body in {
        "timeout": 'shift 2\nexec "$@"\n',
        "sudo": f'echo {"this-unit" if leader else "other-unit"}\n',
        "hostname": "echo this-unit\n",
        "python": f'printf "%s\\n" "$@" "$DOT_PIOREACTOR" "$SKIP_PLUGINS" > "{record}"\n',
    }.items():
        executable = executable_dir / name
        executable.write_text("#!/bin/bash\n" + body)
        executable.chmod(0o755)
    wrapper = tmp_path / "bootfs_files.sh"
    wrapper.write_text(
        (repo / "packaging/runtime-files/bash/bootfs_files.sh")
        .read_text()
        .replace("source /etc/pioreactor.env", f'source "{env_file}"')
    )
    result = subprocess.run(
        ["/bin/bash", str(wrapper)],
        env={**os.environ, "PATH": f"{executable_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    if configured:
        assert record.read_text().splitlines() == [
            "-m",
            "pioreactor.boot_files",
            "leader" if leader else "worker",
            str(data),
            "1",
        ]
    else:
        assert not record.exists()


def test_release_sidecars_match_runtime_assets() -> None:
    repo = Path(__file__).parents[2]
    upcoming = repo / "core/update_scripts/upcoming"
    runtime = repo / "packaging/runtime-files"
    for directory, name in [("bash", "bootfs_files.sh"), ("systemd", "bootfs_files.service")]:
        assert (upcoming / name).read_bytes() == (runtime / directory / name).read_bytes()
    assert 'bash "$SCRIPT_DIR/30_install_bootfs_files.sh"' in (upcoming / "update.sh").read_text()
    assert "Wants=bootfs_files.service" in (upcoming / "bootfs_files.conf").read_text()
