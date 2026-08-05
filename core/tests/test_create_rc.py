# -*- coding: utf-8 -*-
import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import call
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
CREATE_RC_PATH = REPO_ROOT / "scripts" / "create_rc.py"


def load_create_rc_module():
    spec = importlib.util.spec_from_file_location("create_rc", CREATE_RC_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {CREATE_RC_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_get_previous_series_floor_version_for_rc() -> None:
    create_rc = load_create_rc_module()

    assert create_rc.get_minimum_required_version_for_rc("26.4.0rc2") == "26.3.0"


def test_get_previous_series_floor_version_rolls_back_year() -> None:
    create_rc = load_create_rc_module()

    assert create_rc.get_minimum_required_version_for_rc("26.1.0rc1") == "25.12.0"


def test_non_rc_versions_keep_same_series_floor() -> None:
    create_rc = load_create_rc_module()

    assert create_rc.get_series_floor_version("26.4.1") == "26.4.0"


def test_patch_rc_uses_same_series_floor() -> None:
    create_rc = load_create_rc_module()

    assert create_rc.get_minimum_required_version_for_rc("26.5.3rc1") == "26.5.0"


def test_ensure_pre_update_script_uses_previous_series_floor(tmp_path: Path) -> None:
    create_rc = load_create_rc_module()
    create_rc.UPDATE_SCRIPTS_DIR = tmp_path

    changed = create_rc.ensure_pre_update_script("26.4.0rc2", dry_run=False)

    assert changed is True
    contents = (tmp_path / "upcoming" / "pre_update.sh").read_text(encoding="utf-8")
    assert 'min_version="26.3.0"' in contents


def test_ensure_pre_update_script_uses_same_series_floor_for_patch_rc(tmp_path: Path) -> None:
    create_rc = load_create_rc_module()
    create_rc.UPDATE_SCRIPTS_DIR = tmp_path

    changed = create_rc.ensure_pre_update_script("26.5.3rc1", dry_run=False)

    assert changed is True
    contents = (tmp_path / "upcoming" / "pre_update.sh").read_text(encoding="utf-8")
    assert 'min_version="26.5.0"' in contents


def test_ensure_frontend_build_runs_frontend_build_make_target() -> None:
    create_rc = load_create_rc_module()

    with patch.object(
        create_rc.subprocess,
        "run",
        side_effect=[
            subprocess.CompletedProcess(["make", "frontend-build"], returncode=0),
            subprocess.CompletedProcess(["git", "diff", "--quiet"], returncode=0),
        ],
    ) as run:
        changed = create_rc.ensure_frontend_build_is_up_to_date(dry_run=False)

    assert changed is True
    assert run.call_args_list == [
        call(["make", "frontend-build"], check=True),
        call(["git", "diff", "--quiet"], check=False),
    ]


def test_declining_version_confirmation_aborts_before_branch_check() -> None:
    create_rc = load_create_rc_module()

    with (
        patch.object(create_rc, "assert_git_repo"),
        patch.object(create_rc, "compute_rc_version", return_value=("26.8.0", "26.8.0rc1")),
        patch("builtins.input", return_value="n") as prompt,
        patch.object(create_rc, "get_current_git_branch") as get_current_git_branch,
        patch("builtins.print") as print_output,
    ):
        result = create_rc.main([])

    assert result == 1
    prompt.assert_called_once_with("Confirm version 26.8.0rc1? y/n: ")
    get_current_git_branch.assert_not_called()
    print_output.assert_called_once_with(
        'Aborted. Re-run with ARGS="--series YY.M --rc N" to choose a different version.'
    )
