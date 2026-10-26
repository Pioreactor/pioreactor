# -*- coding: utf-8 -*-
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("is_leader", [True, False])
def test_flush_update_removes_descriptors_and_preserves_profiles(tmp_path: Path, is_leader: bool) -> None:
    payload = Path(__file__).parents[1] / "update_scripts/upcoming"
    data = tmp_path / "data"
    jobs = data / "ui/jobs"
    jobs.mkdir(parents=True)
    retired = [jobs / "14_circulate_media.yaml", jobs / "15_circulate_alt_media.yaml"]
    for descriptor in retired:
        descriptor.write_text("retired", encoding="utf-8")
    custom = jobs / "custom.yaml"
    custom.write_text("custom", encoding="utf-8")

    script = tmp_path / "update.sh"
    script.write_text(
        (payload / "70_replace_circulation_with_flush.sh")
        .read_text(encoding="utf-8")
        .replace('DOT_PIOREACTOR="/home/pioreactor/.pioreactor"', f'DOT_PIOREACTOR="{data}"'),
        encoding="utf-8",
    )
    (tmp_path / "flush.yaml").write_bytes((payload / "flush.yaml").read_bytes())

    # Exercise filesystem changes without root or Linux-only account names.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {
        "sudo": "echo leader",
        "hostname": "echo leader" if is_leader else "echo worker",
        "install": """args=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o|-g) shift 2 ;;
        *) args+=("$1"); shift ;;
    esac
done
exec /usr/bin/install "${args[@]}"
""",
    }
    for name, body in stubs.items():
        executable = bin_dir / name
        executable.write_text(f"#!/bin/bash\nset -eu\n{body}\n", encoding="utf-8")
        executable.chmod(0o755)
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

    subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True)
    assert not any(descriptor.exists() for descriptor in retired)
    assert custom.read_text(encoding="utf-8") == "custom"
    profile = data / "experiment_profiles/flush.yaml"
    assert profile.exists() == is_leader

    if is_leader:
        assert profile.read_bytes() == (payload / "flush.yaml").read_bytes()
        profile.write_text("user's customized profile", encoding="utf-8")

    subprocess.run(["bash", str(script)], env=env, check=True, capture_output=True)
    if is_leader:
        assert profile.read_text(encoding="utf-8") == "user's customized profile"

        # A missing or empty sidecar must never create a broken installed profile.
        profile.unlink()
        for empty in (True, False):
            asset = tmp_path / "flush.yaml"
            if empty:
                asset.write_text("", encoding="utf-8")
            else:
                asset.unlink()
            result = subprocess.run(["bash", str(script)], env=env, capture_output=True)
            assert result.returncode != 0
            assert not profile.exists()
