# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["create_rc", "create_release", "create_hotfix_release"])
def release_helper(request: pytest.FixtureRequest, tmp_path: Path) -> ModuleType:
    script = REPO_ROOT / "scripts" / f"{request.param}.py"
    spec = importlib.util.spec_from_file_location(request.param, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.VERSION_FILE = tmp_path / "version.py"
    return module


@pytest.mark.parametrize("version", ["25.12.2.dev0", "25.12.2rc1", "25.12.2"])
def test_default_series_comes_from_version_file(release_helper: ModuleType, version: str) -> None:
    release_helper.VERSION_FILE.write_text(f'__version__ = "{version}"\n', encoding="utf-8")

    assert release_helper.compute_series() == "25.12"


def test_explicit_series_does_not_require_version_file(release_helper: ModuleType) -> None:
    assert release_helper.compute_series("27.1") == "27.1"


def test_invalid_series_override_is_rejected(release_helper: ModuleType) -> None:
    with pytest.raises(ValueError, match="--series must be in format YY.M"):
        release_helper.compute_series("invalid")
