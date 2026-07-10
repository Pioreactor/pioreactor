# -*- coding: utf-8 -*-
import sys
from pathlib import Path

import pytest
from pioreactor.plugin_management.utils import discover_plugins_in_local_folder


def test_discover_plugins_in_local_folder_does_not_duplicate_sys_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins_dev = tmp_path / "plugins_dev"
    plugins_dev.mkdir()
    (plugins_dev / "demo_plugin.py").write_text("__plugin_name__ = 'demo'\n", encoding="utf-8")
    monkeypatch.setenv("PLUGINS_DEV", str(plugins_dev))

    original_sys_path = list(sys.path)
    monkeypatch.setattr(sys, "path", original_sys_path.copy())

    discover_plugins_in_local_folder()
    discover_plugins_in_local_folder()

    assert sys.path.count(str(plugins_dev)) == 1
