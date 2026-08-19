# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import site
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

from pioreactor.config import ConfigParserMod
from pioreactor.config import get_config
from pioreactor.config import replace_or_append_config_entry
from pioreactor.paths import get_dot_pioreactor_path
from pioreactor.whoami import am_I_leader

if TYPE_CHECKING:
    from pioreactor.logging import CustomLogger


def clean_plugin_name_for_pip(plugin_name: str) -> str:
    return plugin_name.lower().replace("_", "-")


def clean_plugin_name_for_package_dir(plugin_name: str) -> str:
    return plugin_name.lower().replace("-", "_")


def get_site_packages_dir() -> Path:
    return Path(site.getsitepackages()[0])


def get_dot_pioreactor_dir() -> Path:
    return get_dot_pioreactor_path()


def get_pioreactor_database_path() -> Path:
    return Path(get_config().get("storage", "database"))


def install_plugin_package(plugin_name: str, source: str | None, *, is_leader: bool | None = None) -> bool:
    pip_plugin_name = clean_plugin_name_for_pip(plugin_name)

    if source:
        run_pip_as_pioreactor(["install", "--force-reinstall", "--no-deps", source])
        return True
    else:
        is_leader = am_I_leader() if is_leader is None else is_leader

        if package_is_leader_only(pip_plugin_name) and not is_leader:
            return False

        run_pip_as_pioreactor(
            [
                "install",
                "--upgrade",
                "--force-reinstall",
                "--ignore-installed",
                pip_plugin_name,
            ]
        )
        return True


def run_pip_as_pioreactor(
    arguments: list[str], *, capture_output: bool = False, text: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sudo", "-u", "pioreactor", sys.executable, "-m", "pip", *arguments],
        capture_output=capture_output,
        check=not capture_output,
        text=text,
    )


def package_is_leader_only(plugin_name: str) -> bool:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        run_pip_as_pioreactor(
            [
                "download",
                "-qq",
                "--no-deps",
                "--dest",
                str(tmp_path),
                plugin_name,
            ]
        )

        wheel_paths = list(tmp_path.glob(f"{clean_plugin_name_for_package_dir(plugin_name)}*.whl"))
        if not wheel_paths:
            raise FileNotFoundError(f"pip download did not produce a wheel for {plugin_name}")

        with zipfile.ZipFile(wheel_paths[0]) as wheel:
            return "LEADER_ONLY" in wheel.namelist()


def get_plugin_install_folder(plugin_name: str, site_packages_dir: Path) -> Path:
    plugin_module_roots = {
        entry_point.module.partition(".")[0]
        for entry_point in metadata.distribution(plugin_name).entry_points
        if entry_point.group == "pioreactor.plugins"
    }

    if len(plugin_module_roots) != 1:
        raise ValueError(
            f"Plugin {plugin_name} must declare exactly one Python package in its "
            "pioreactor.plugins entry points."
        )

    install_folder = site_packages_dir / plugin_module_roots.pop()
    if not install_folder.is_dir():
        raise FileNotFoundError(f"Plugin package directory does not exist: {install_folder}")

    return install_folder


def install_plugin_assets(
    plugin_name: str,
    logger: CustomLogger,
    *,
    dot_pioreactor_dir: Path | None = None,
    site_packages_dir: Path | None = None,
    database_path: Path | None = None,
    is_leader: bool | None = None,
) -> None:
    dot_pioreactor_dir = dot_pioreactor_dir or get_dot_pioreactor_dir()
    site_packages_dir = site_packages_dir or get_site_packages_dir()
    database_path = database_path or get_pioreactor_database_path()
    is_leader = am_I_leader() if is_leader is None else is_leader

    install_folder = get_plugin_install_folder(plugin_name, site_packages_dir)
    logger.debug(f"Resolved plugin {plugin_name} package directory to {install_folder}.")

    merge_plugin_ui_assets(install_folder, dot_pioreactor_dir)
    merge_additional_config(install_folder, dot_pioreactor_dir, is_leader=is_leader)

    if is_leader:
        sql_was_applied = apply_additional_sql(install_folder, database_path)
        export_dataset_was_added = merge_exportable_dataset_assets(install_folder, dot_pioreactor_dir)

        if export_dataset_was_added:
            logger.debug("Added exportable_datasets.")

        if sql_was_applied:
            logger.debug("Applied SQL statement. Attempting to restart mqtt_to_db_streaming.")
            restart_mqtt_to_db_streaming()

    run_post_install_hook(install_folder, logger)
    ensure_dot_pioreactor_tree_group_is_www_data(dot_pioreactor_dir)


def uninstall_plugin_assets(
    plugin_name: str,
    logger: CustomLogger,
    *,
    dot_pioreactor_dir: Path | None = None,
    site_packages_dir: Path | None = None,
    is_leader: bool | None = None,
) -> None:
    dot_pioreactor_dir = dot_pioreactor_dir or get_dot_pioreactor_dir()
    site_packages_dir = site_packages_dir or get_site_packages_dir()
    is_leader = am_I_leader() if is_leader is None else is_leader

    try:
        install_folder = get_plugin_install_folder(plugin_name, site_packages_dir)
    except metadata.PackageNotFoundError:
        logger.debug(f"Distribution metadata for plugin {plugin_name} was not found; skipping asset cleanup.")
        return
    except FileNotFoundError:
        logger.debug(
            f"Plugin package directory for plugin {plugin_name} was not found; skipping asset cleanup."
        )
        return

    logger.debug(f"Resolved plugin {plugin_name} package directory to {install_folder}.")

    run_pre_uninstall_hook(install_folder, logger)
    remove_plugin_ui_assets(install_folder, dot_pioreactor_dir)

    if is_leader:
        remove_exportable_dataset_assets(install_folder, dot_pioreactor_dir)


def uninstall_plugin_package(plugin_name: str) -> subprocess.CompletedProcess[str]:
    pip_plugin_name = clean_plugin_name_for_pip(plugin_name)
    return run_pip_as_pioreactor(["uninstall", "-y", pip_plugin_name], capture_output=True, text=True)


def merge_plugin_ui_assets(install_folder: Path, dot_pioreactor_dir: Path) -> None:
    legacy_contrib_dir = install_folder / "ui" / "contrib"
    ui_dir = install_folder / "ui"

    if legacy_contrib_dir.is_dir():
        copy_tree_contents(legacy_contrib_dir, dot_pioreactor_dir / "plugins" / "ui")
    elif ui_dir.is_dir():
        copy_tree_contents(ui_dir, dot_pioreactor_dir / "plugins" / "ui")


def merge_exportable_dataset_assets(install_folder: Path, dot_pioreactor_dir: Path) -> bool:
    datasets_dir = install_folder / "exportable_datasets"

    if datasets_dir.is_dir():
        copy_tree_contents(datasets_dir, dot_pioreactor_dir / "plugins" / "exportable_datasets")
        return True
    return False


def remove_plugin_ui_assets(install_folder: Path, dot_pioreactor_dir: Path) -> None:
    legacy_contrib_dir = install_folder / "ui" / "contrib"
    ui_dir = install_folder / "ui"

    if legacy_contrib_dir.is_dir():
        remove_tree_files(legacy_contrib_dir, dot_pioreactor_dir / "plugins" / "ui")
    elif ui_dir.is_dir():
        remove_tree_files(ui_dir, dot_pioreactor_dir / "plugins" / "ui")


def remove_exportable_dataset_assets(install_folder: Path, dot_pioreactor_dir: Path) -> None:
    datasets_dir = install_folder / "exportable_datasets"

    if datasets_dir.is_dir():
        remove_tree_files(datasets_dir, dot_pioreactor_dir / "plugins" / "exportable_datasets")


def copy_tree_contents(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)

    for source_path in source_dir.iterdir():
        destination_path = destination_dir / source_path.name
        if source_path.is_dir():
            shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, destination_path)


def remove_tree_files(source_dir: Path, destination_dir: Path) -> None:
    for source_path in source_dir.rglob("*"):
        if source_path.is_file():
            destination_path = destination_dir / source_path.relative_to(source_dir)
            destination_path.unlink(missing_ok=True)


def merge_additional_config(install_folder: Path, dot_pioreactor_dir: Path, *, is_leader: bool) -> None:
    """Merge unit runtime config locally and dotted UI config into the leader's shared config."""
    additional_config_path = install_folder / "additional_config.ini"

    if not additional_config_path.exists():
        return

    additional_config = ConfigParserMod()
    additional_config.read(additional_config_path)

    unit_config_path = dot_pioreactor_dir / "unit_config.ini"
    unit_config = ConfigParserMod()
    unit_config.read(unit_config_path)

    # Dotted ui.* sections are leader-owned UI state and must never become unit overrides.
    for section in additional_config.sections():
        if section.startswith("ui."):
            continue

        if not unit_config.has_section(section):
            unit_config.add_section(section)

        for option, value in additional_config.items(section, raw=True):
            unit_config.set(section, option, value)

    with unit_config_path.open("w", encoding="utf-8") as file:
        unit_config.write(file)

    if not is_leader:
        return

    shared_config_path = dot_pioreactor_dir / "config.ini"
    shared_config_text = shared_config_path.read_text(encoding="utf-8")
    original_shared_config_text = shared_config_text
    shared_config = ConfigParserMod()
    shared_config.read_string(shared_config_text)

    # add the [ui.*] sections to the leader's shared config so the UI reads it.
    for section in additional_config.sections():
        if not section.startswith("ui."):
            continue

        if not shared_config.has_section(section):
            shared_config.add_section(section)

        for option, value in additional_config.items(section, raw=True):
            if shared_config.has_option(section, option):
                continue

            shared_config_text = replace_or_append_config_entry(shared_config_text, section, option, value)
            shared_config.set(section, option, value)

    if shared_config_text == original_shared_config_text:
        return

    existing_mode = shared_config_path.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=shared_config_path.parent,
        delete=False,
    ) as temporary_file:
        temporary_file.write(shared_config_text)
        os.fchmod(temporary_file.fileno(), existing_mode)
        temporary_path = Path(temporary_file.name)

    temporary_path.replace(shared_config_path)


def apply_additional_sql(install_folder: Path, database_path: Path) -> bool:
    additional_sql_path = install_folder / "additional_sql.sql"

    if not additional_sql_path.exists():
        return False

    sql = additional_sql_path.read_text(encoding="utf-8")
    with sqlite3.connect(database_path) as db:
        db.executescript(sql)

    return True


def restart_mqtt_to_db_streaming() -> None:
    subprocess.run(
        ["sudo", "systemctl", "restart", "pioreactor_startup_run@mqtt_to_db_streaming.service"],
        check=True,
    )


def run_post_install_hook(install_folder: Path, logger: CustomLogger) -> None:
    post_install_path = install_folder / "post_install.sh"

    if post_install_path.exists():
        logger.debug(f"Running plugin post-install hook {post_install_path}.")
        subprocess.run(["bash", str(post_install_path)], check=True)
        logger.debug(f"Completed plugin post-install hook {post_install_path}.")
    else:
        logger.debug(f"No plugin post-install hook found at {post_install_path}.")


def run_pre_uninstall_hook(install_folder: Path, logger: CustomLogger) -> None:
    pre_uninstall_path = install_folder / "pre_uninstall.sh"

    if pre_uninstall_path.exists():
        logger.debug(f"Running plugin pre-uninstall hook {pre_uninstall_path}.")
        subprocess.run(["sudo", "bash", str(pre_uninstall_path)], check=False)
        logger.debug(f"Completed plugin pre-uninstall hook {pre_uninstall_path}.")
    else:
        logger.debug(f"No plugin pre-uninstall hook found at {pre_uninstall_path}.")


def ensure_dot_pioreactor_tree_group_is_www_data(dot_pioreactor_dir: Path) -> None:
    if not dot_pioreactor_dir.is_dir():
        return

    subprocess.run(
        [
            "sudo",
            "chown",
            "-R",
            "pioreactor:www-data",
            str(dot_pioreactor_dir),
        ],
        check=True,
    )
    dot_pioreactor_dir.chmod(dot_pioreactor_dir.stat().st_mode | 0o020)
    subprocess.run(["sudo", "chmod", "-R", "g+w", str(dot_pioreactor_dir)], check=True)
    subprocess.run(
        ["sudo", "find", str(dot_pioreactor_dir), "-type", "d", "-exec", "chmod", "g+s", "{}", "+"],
        check=True,
    )
