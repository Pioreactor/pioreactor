# -*- coding: utf-8 -*-
from __future__ import annotations

import zipfile
from pathlib import Path

from pioreactor.plugin_management.utils import get_package_plugin_display_name
from pioreactor.plugin_management.utils import get_plugin_artifact_display_name


def test_python_plugin_file_uses_plugin_name_without_importing(tmp_path: Path) -> None:
    py_file = tmp_path / "my_plugin.py"
    py_file.write_text('raise RuntimeError("imported")\n__plugin_name__ = "My plugin"\n')

    assert get_plugin_artifact_display_name(py_file) == "My plugin"


def test_python_plugin_file_falls_back_to_stem(tmp_path: Path) -> None:
    py_file = tmp_path / "my_plugin.py"
    py_file.write_text("__plugin_version__ = '1.0'\n")

    assert get_plugin_artifact_display_name(py_file) == "my_plugin"


def test_wheel_uses_metadata_name(tmp_path: Path) -> None:
    wheel = tmp_path / "pioreactor_air_bubbler-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "pioreactor_air_bubbler-1.0.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: Pioreactor-Air-Bubbler\nVersion: 1.0.0\n",
        )

    assert get_plugin_artifact_display_name(wheel) == "Pioreactor-Air-Bubbler"


def test_unreadable_wheel_falls_back_to_filename(tmp_path: Path) -> None:
    wheel = tmp_path / "pioreactor_air_bubbler-1.0.0-py3-none-any.whl"
    wheel.write_bytes(b"not a zip")

    assert get_plugin_artifact_display_name(wheel) == "pioreactor-air-bubbler"


def test_package_display_name_uses_distribution_metadata() -> None:
    assert get_package_plugin_display_name("MSGSPEC") == "msgspec"
    assert get_package_plugin_display_name("not-a-real-plugin") == "not-a-real-plugin"
