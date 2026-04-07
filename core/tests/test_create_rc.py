# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path


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


def test_ensure_pre_update_script_uses_previous_series_floor(tmp_path: Path) -> None:
    create_rc = load_create_rc_module()
    create_rc.UPDATE_SCRIPTS_DIR = tmp_path

    changed = create_rc.ensure_pre_update_script("26.4.0rc2", dry_run=False)

    assert changed is True
    contents = (tmp_path / "upcoming" / "pre_update.sh").read_text(encoding="utf-8")
    assert 'min_version="26.3.0"' in contents
