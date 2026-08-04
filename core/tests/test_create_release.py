# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
CREATE_RELEASE_PATH = REPO_ROOT / "scripts" / "create_release.py"


def load_create_release_module():
    spec = importlib.util.spec_from_file_location("create_release", CREATE_RELEASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {CREATE_RELEASE_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_first_release_uses_previous_series_floor() -> None:
    create_release = load_create_release_module()

    assert create_release.get_minimum_required_version_for_release("26.4.0") == "26.3.0"


def test_first_release_rolls_back_year() -> None:
    create_release = load_create_release_module()

    assert create_release.get_minimum_required_version_for_release("26.1.0") == "25.12.0"


def test_hotfix_release_uses_same_series_floor() -> None:
    create_release = load_create_release_module()

    assert create_release.get_minimum_required_version_for_release("26.4.1") == "26.4.0"


def test_ensure_pre_update_script_uses_previous_series_floor_for_first_release(tmp_path: Path) -> None:
    create_release = load_create_release_module()
    create_release.UPDATE_SCRIPTS_DIR = tmp_path

    changed = create_release.ensure_pre_update_script("26.4.0", dry_run=False)

    assert changed is True
    contents = (tmp_path / "upcoming" / "pre_update.sh").read_text(encoding="utf-8")
    assert 'min_version="26.3.0"' in contents


def test_declining_version_confirmation_aborts_before_branch_check() -> None:
    create_release = load_create_release_module()

    with (
        patch.object(create_release, "assert_git_repo"),
        patch.object(create_release, "compute_series", return_value="26.8"),
        patch.object(create_release, "read_version_value", return_value="26.8.0.dev0"),
        patch.object(create_release, "determine_release_base", return_value="26.8.0"),
        patch("builtins.input", return_value="n") as prompt,
        patch.object(create_release, "get_current_git_branch") as get_current_git_branch,
        patch("builtins.print") as print_output,
    ):
        result = create_release.main([])

    assert result == 1
    prompt.assert_called_once_with("Confirm version 26.8.0? y/n: ")
    get_current_git_branch.assert_not_called()
    print_output.assert_called_once_with(
        'Aborted. Re-run with ARGS="--series YY.M" to choose a different release series.'
    )
