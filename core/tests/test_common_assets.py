# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "packaging/runtime-files/bash/install_common_assets.sh"
STAGER = REPO_ROOT / "scripts/stage_common_assets.sh"


@pytest.fixture
def payload(tmp_path: Path) -> Path:
    assets = tmp_path / "assets"
    subprocess.run(["bash", str(STAGER), str(assets)], check=True)
    return assets


@pytest.fixture
def install_env(tmp_path: Path) -> dict[str, str]:
    # Exercise real filesystem installation as an ordinary user. Only ownership
    # flags are stripped; production uses root and the real pioreactor/www-data IDs.
    real_install = shutil.which("install")
    assert real_install is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "install"
    wrapper.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "args = iter(sys.argv[1:])\n"
        "filtered = []\n"
        "for arg in args:\n"
        "    if arg in ('-o', '-g'):\n"
        "        next(args)\n"
        "    else:\n"
        "        filtered.append(arg)\n"
        f"os.execv({real_install!r}, [{real_install!r}, *filtered])\n"
    )
    wrapper.chmod(0o755)
    # Any attempt to manage services makes the installation fail.
    systemctl = bin_dir / "systemctl"
    systemctl.write_text("#!/bin/sh\nexit 99\n")
    systemctl.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}


def install(payload: Path, root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALLER), str(payload), str(root)], env=env, capture_output=True, text=True
    )


def test_fresh_install_retry_and_partial_recovery(
    payload: Path, install_env: dict[str, str], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    result = install(payload, root, install_env)
    assert result.returncode == 0, result.stderr
    for row in (payload / "common-assets.tsv").read_text().splitlines():
        asset, destination, _, _, mode = row.split("\t")
        target = root / destination.lstrip("/")
        assert target.read_bytes() == (payload / asset).read_bytes()
        assert target.stat().st_mode & 0o777 == int(mode, 8)
    data = root / "home/pioreactor/.pioreactor"
    assert (data / "plugins/ui/charts").is_dir()
    assert (data / "plugins/exportable_datasets").is_dir()
    assert not (data / "config.ini").exists()
    assert not (data / "storage").exists()
    assert not (data / "hardware").exists()
    assert (data / "camera/ov5647_noir_200ms.json").is_file()
    assert not (root / "etc").exists()

    chart = data / "ui/charts/05_od.yaml"
    original_mtime = chart.stat().st_mtime_ns
    assert install(payload, root, install_env).returncode == 0
    assert chart.stat().st_mtime_ns == original_mtime
    chart.unlink()
    assert install(payload, root, install_env).returncode == 0
    assert chart.is_file()


def test_preserves_existing_worker_or_leader_files(
    payload: Path, install_env: dict[str, str], tmp_path: Path
) -> None:
    root = tmp_path / "root"
    data = root / "home/pioreactor/.pioreactor"
    originals = {
        data / "config.ini": b"[cluster.topology]\nleader_hostname=existing\n",
        data / "unit_config.ini": b"# unit overrides\n",
        data / "storage/pioreactor.sqlite": b"existing database",
        data / "ui/charts/05_od.yaml": b"customized descriptor",
        data / "camera/ov5647_noir_200ms.json": b"custom camera tuning",
        data / "hardware/hats/1.1/adc.yaml": b"custom hardware wiring",
        root / "etc/mosquitto/mosquitto.conf": b"existing broker config",
        root / "etc/systemd/system/avahi_aliases.service": b"custom service",
    }
    for path, content in originals.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    link = data / "ui/charts/06_temperature.yaml"
    link.symlink_to("missing-custom-chart.yaml")
    result = install(payload, root, install_env)
    assert result.returncode == 0, result.stderr
    assert link.is_symlink()
    for path, content in originals.items():
        assert path.read_bytes() == content
    # An intentionally absent capability file must stay absent on upgrade.
    assert not (data / "hardware/models/pioreactor_20ml/1.5/adc.yaml").exists()


def test_missing_asset_fails_before_installing_anything(
    payload: Path, install_env: dict[str, str], tmp_path: Path
) -> None:
    last_asset = (payload / "common-assets.tsv").read_text().splitlines()[-1].split("\t")[0]
    (payload / last_asset).unlink()
    root = tmp_path / "root"
    root.mkdir()
    assert install(payload, root, install_env).returncode != 0
    assert list(root.iterdir()) == []


def test_release_payload_matches_shared_sources(payload: Path) -> None:
    # Release snapshots remain inspectable and flat; regeneration must not drift
    # from the payload used by the image builder.
    upcoming = REPO_ROOT / "core/update_scripts/upcoming"
    if not (upcoming / "common-assets.tsv").exists():
        pytest.skip("Installation parity between roles payload has already been released.")
    for asset in payload.iterdir():
        assert (upcoming / asset.name).read_bytes() == asset.read_bytes(), asset.name
