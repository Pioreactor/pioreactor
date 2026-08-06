# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from pioreactor.config import ConfigParserMod
from pioreactor.plugin_management import install_plugin as install_plugin_module
from pioreactor.plugin_management import package_operations
from pioreactor.plugin_management import uninstall_plugin as uninstall_plugin_module


class PluginPackageEnvironment:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.dot_pioreactor = tmp_path / "dot_pioreactor"
        self.site_packages = tmp_path / "site-packages"
        self.database = tmp_path / "pioreactor.sqlite"
        self.command_log = tmp_path / "commands.log"

        self.plugin_name = "pioreactor-demo-plugin"
        self.package_dir_name = "pioreactor_demo_plugin"
        self.install_folder = self.site_packages / self.package_dir_name

    def prepare(self) -> None:
        self.dot_pioreactor.mkdir()
        self.site_packages.mkdir()
        self.database.touch()
        (self.dot_pioreactor / "plugins" / "ui").mkdir(parents=True)
        (self.dot_pioreactor / "plugins" / "exportable_datasets").mkdir(parents=True)
        (self.dot_pioreactor / "config.ini").write_text(
            """# Preserve shared config comments.
[ui.overview.charts]
operator_hidden_chart=0
""",
            encoding="utf-8",
        )
        (self.dot_pioreactor / "unit_config.ini").write_text("", encoding="utf-8")
        self.install_folder.mkdir()

    def create_plugin_payload(self, *, use_legacy_ui_contrib: bool = True) -> None:
        ui_root = self.install_folder / "ui"
        if use_legacy_ui_contrib:
            ui_root = ui_root / "contrib"

        (ui_root / "cards").mkdir(parents=True)
        (ui_root / "cards" / "demo.yaml").write_text("name: demo-card\n", encoding="utf-8")

        (self.install_folder / "exportable_datasets").mkdir()
        (self.install_folder / "exportable_datasets" / "demo.yaml").write_text(
            "dataset: demo\n", encoding="utf-8"
        )

        (self.install_folder / "additional_config.ini").write_text(
            "[demo]\nenabled=1\nCamelCaseKey=ok\n", encoding="utf-8"
        )
        (self.install_folder / "additional_sql.sql").write_text(
            "CREATE TABLE demo_plugin_table (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
        )
        (self.install_folder / "post_install.sh").write_text(
            f"#!/bin/bash\nprintf post_install >> {self.root / 'post_install.log'}\n",
            encoding="utf-8",
        )
        (self.install_folder / "post_install.sh").chmod(0o755)
        (self.install_folder / "pre_uninstall.sh").write_text(
            f"#!/bin/bash\nprintf pre_uninstall >> {self.root / 'pre_uninstall.log'}\n",
            encoding="utf-8",
        )
        (self.install_folder / "pre_uninstall.sh").chmod(0o755)

    def run_python_install(
        self, source: str | None, monkeypatch: pytest.MonkeyPatch
    ) -> subprocess.CompletedProcess[str]:
        self.patch_python_subprocess(monkeypatch)

        try:
            package_operations.install_plugin_package(self.plugin_name, source)
            package_operations.install_plugin_assets(
                self.plugin_name,
                dot_pioreactor_dir=self.dot_pioreactor,
                site_packages_dir=self.site_packages,
                database_path=self.database,
                is_leader=True,
            )
            return subprocess.CompletedProcess([self.plugin_name, source or ""], 0, "", "")
        except Exception as exc:
            return subprocess.CompletedProcess([self.plugin_name, source or ""], 1, "", str(exc))

    def run_python_uninstall(self, monkeypatch: pytest.MonkeyPatch) -> subprocess.CompletedProcess[str]:
        self.patch_python_subprocess(monkeypatch)

        try:
            package_operations.uninstall_plugin_assets(
                self.plugin_name,
                dot_pioreactor_dir=self.dot_pioreactor,
                site_packages_dir=self.site_packages,
                is_leader=True,
            )
            result = package_operations.uninstall_plugin_package(self.plugin_name)
            return result
        except Exception as exc:
            return subprocess.CompletedProcess([self.plugin_name], 1, "", str(exc))

    def patch_python_subprocess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_subprocess_run = subprocess.run

        def fake_subprocess_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[:6] == ["sudo", "-u", "pioreactor", sys.executable, "-m", "pip"]:
                self.append_command_log(f"pip {' '.join(args[6:])}\n")
                return subprocess.CompletedProcess(args, 0, "", "")

            if args == [
                "sudo",
                "systemctl",
                "restart",
                "pioreactor_startup_run@mqtt_to_db_streaming.service",
            ]:
                self.append_command_log(
                    "systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service\n"
                )
                return subprocess.CompletedProcess(args, 0, "", "")

            if len(args) == 3 and args[:2] == ["sudo", "bash"]:
                return real_subprocess_run(["bash", args[2]], **kwargs)

            if args and args[0] == "sudo":
                return subprocess.CompletedProcess(args, 0, "", "")

            if args and args[0] == "bash":
                return real_subprocess_run(args, **kwargs)

            raise AssertionError(f"Unexpected subprocess call: {args}")

        monkeypatch.setattr(package_operations.subprocess, "run", fake_subprocess_run)

    def append_command_log(self, content: str) -> None:
        with self.command_log.open("a", encoding="utf-8") as file:
            file.write(content)


@pytest.fixture()
def plugin_package_environment(tmp_path: Path) -> PluginPackageEnvironment:
    environment = PluginPackageEnvironment(tmp_path)
    environment.prepare()
    return environment


def test_python_plugin_package_environment_exercises_full_leader_merge_contract(
    plugin_package_environment: PluginPackageEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_package_environment.create_plugin_payload()

    result = plugin_package_environment.run_python_install("file:///tmp/demo.whl", monkeypatch)

    assert result.returncode == 0, result.stderr
    assert_plugin_install_contract(plugin_package_environment)

    with sqlite3.connect(plugin_package_environment.database) as db:
        table_exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'demo_plugin_table'"
        ).fetchone()
    assert table_exists == (1,)


def test_plugin_config_routes_ui_sections_to_shared_config_on_leader(
    plugin_package_environment: PluginPackageEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_package_environment.create_plugin_payload()
    (plugin_package_environment.install_folder / "additional_config.ini").write_text(
        "[demo]\n"
        "enabled=1\n"
        "\n"
        "[ui.overview.charts]\n"
        "operator_hidden_chart=1\n"
        "demo_chart=1\n"
        "\n"
        "[ui.demo]\n"
        "CamelCaseUiKey=ok\n",
        encoding="utf-8",
    )

    result = plugin_package_environment.run_python_install("file:///tmp/demo.whl", monkeypatch)

    assert result.returncode == 0, result.stderr
    shared_config_text = (plugin_package_environment.dot_pioreactor / "config.ini").read_text(
        encoding="utf-8"
    )
    assert "# Preserve shared config comments." in shared_config_text

    shared_config = ConfigParserMod()
    shared_config.read(plugin_package_environment.dot_pioreactor / "config.ini")
    assert shared_config.get("ui.overview.charts", "operator_hidden_chart") == "0"
    assert shared_config.get("ui.overview.charts", "demo_chart") == "1"
    assert shared_config.get("ui.demo", "CamelCaseUiKey") == "ok"

    unit_config = ConfigParserMod()
    unit_config.read(plugin_package_environment.dot_pioreactor / "unit_config.ini")
    assert unit_config.get("demo", "enabled") == "1"
    assert not unit_config.has_section("ui.overview.charts")
    assert not unit_config.has_section("ui.demo")


def test_plugin_config_ignores_ui_sections_on_worker(
    plugin_package_environment: PluginPackageEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_package_environment.create_plugin_payload()
    (plugin_package_environment.install_folder / "additional_config.ini").write_text(
        """[demo]
enabled=1

[ui.overview.charts]
demo_chart=1
""",
        encoding="utf-8",
    )
    plugin_package_environment.patch_python_subprocess(monkeypatch)
    original_shared_config = (plugin_package_environment.dot_pioreactor / "config.ini").read_text(
        encoding="utf-8"
    )

    package_operations.install_plugin_assets(
        plugin_package_environment.plugin_name,
        dot_pioreactor_dir=plugin_package_environment.dot_pioreactor,
        site_packages_dir=plugin_package_environment.site_packages,
        database_path=plugin_package_environment.database,
        is_leader=False,
    )

    assert (plugin_package_environment.dot_pioreactor / "config.ini").read_text(
        encoding="utf-8"
    ) == original_shared_config
    unit_config = ConfigParserMod()
    unit_config.read(plugin_package_environment.dot_pioreactor / "unit_config.ini")
    assert unit_config.get("demo", "enabled") == "1"
    assert not unit_config.has_section("ui.overview.charts")


def test_python_plugin_uninstall_environment_exercises_full_leader_cleanup_contract(
    plugin_package_environment: PluginPackageEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_package_environment.create_plugin_payload(use_legacy_ui_contrib=False)
    install_result = plugin_package_environment.run_python_install("file:///tmp/demo.whl", monkeypatch)
    assert install_result.returncode == 0, install_result.stderr

    result = plugin_package_environment.run_python_uninstall(monkeypatch)

    assert result.returncode == 0, result.stderr
    assert_plugin_uninstall_contract(plugin_package_environment)


def test_python_plugin_uninstall_removes_legacy_ui_contrib_assets(
    plugin_package_environment: PluginPackageEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_package_environment.create_plugin_payload(use_legacy_ui_contrib=True)
    install_result = plugin_package_environment.run_python_install("file:///tmp/demo.whl", monkeypatch)
    assert install_result.returncode == 0, install_result.stderr
    assert (plugin_package_environment.dot_pioreactor / "plugins" / "ui" / "cards" / "demo.yaml").exists()

    result = plugin_package_environment.run_python_uninstall(monkeypatch)

    assert result.returncode == 0, result.stderr
    assert not (plugin_package_environment.dot_pioreactor / "plugins" / "ui" / "cards" / "demo.yaml").exists()


def test_python_plugin_uninstall_continues_when_pre_uninstall_hook_fails(
    plugin_package_environment: PluginPackageEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_package_environment.create_plugin_payload(use_legacy_ui_contrib=False)
    install_result = plugin_package_environment.run_python_install("file:///tmp/demo.whl", monkeypatch)
    assert install_result.returncode == 0, install_result.stderr
    (plugin_package_environment.install_folder / "pre_uninstall.sh").write_text(
        "#!/bin/bash\nexit 42\n", encoding="utf-8"
    )

    result = plugin_package_environment.run_python_uninstall(monkeypatch)

    assert result.returncode == 0, result.stderr
    assert not (plugin_package_environment.dot_pioreactor / "plugins" / "ui" / "cards" / "demo.yaml").exists()
    command_log = plugin_package_environment.command_log.read_text(encoding="utf-8")
    assert "pip uninstall -y pioreactor-demo-plugin" in command_log


def test_install_plugin_skips_assets_when_leader_only_package_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(install_plugin_module, "install_plugin_package", lambda name, source: False)
    monkeypatch.setattr(
        install_plugin_module,
        "install_plugin_assets",
        lambda name: calls.append(f"assets:{name}"),
    )

    install_plugin_module.install_plugin("pioreactor-leader-only")

    assert calls == []


def test_uninstall_plugin_warns_when_package_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(uninstall_plugin_module, "discover_plugins_in_local_folder", lambda: [])
    monkeypatch.setattr(uninstall_plugin_module, "uninstall_plugin_assets", lambda name: None)
    monkeypatch.setattr(
        uninstall_plugin_module,
        "uninstall_plugin_package",
        lambda name: subprocess.CompletedProcess(
            [name],
            1,
            "",
            "WARNING: Skipping pioreactor-demo-plugin as it is not installed.\n",
        ),
    )

    uninstall_plugin_module.uninstall_plugin("pioreactor-demo-plugin")


def assert_plugin_install_contract(plugin_package_environment: PluginPackageEnvironment) -> None:
    assert (plugin_package_environment.dot_pioreactor / "plugins" / "ui" / "cards" / "demo.yaml").read_text(
        encoding="utf-8"
    ) == "name: demo-card\n"
    assert (
        plugin_package_environment.dot_pioreactor / "plugins" / "exportable_datasets" / "demo.yaml"
    ).read_text(encoding="utf-8") == "dataset: demo\n"
    unit_config = ConfigParserMod()
    unit_config.read(plugin_package_environment.dot_pioreactor / "unit_config.ini")
    assert unit_config.get("demo", "enabled") == "1"
    assert unit_config.get("demo", "CamelCaseKey") == "ok"
    assert (plugin_package_environment.root / "post_install.log").read_text(
        encoding="utf-8"
    ) == "post_install"

    command_log = plugin_package_environment.command_log.read_text(encoding="utf-8")
    assert "pip install --force-reinstall --no-deps file:///tmp/demo.whl" in command_log
    assert "systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service" in command_log


def assert_plugin_uninstall_contract(plugin_package_environment: PluginPackageEnvironment) -> None:
    assert not (plugin_package_environment.dot_pioreactor / "plugins" / "ui" / "cards" / "demo.yaml").exists()
    assert not (
        plugin_package_environment.dot_pioreactor / "plugins" / "exportable_datasets" / "demo.yaml"
    ).exists()
    assert (plugin_package_environment.root / "pre_uninstall.log").read_text(
        encoding="utf-8"
    ) == "pre_uninstall"

    command_log = plugin_package_environment.command_log.read_text(encoding="utf-8")
    assert "pip uninstall -y pioreactor-demo-plugin" in command_log
