# -*- coding: utf-8 -*-
import click
from pioreactor.exc import BashScriptError
from pioreactor.plugin_management.package_operations import uninstall_plugin_assets
from pioreactor.plugin_management.package_operations import uninstall_plugin_package
from pioreactor.plugin_management.utils import discover_plugins_in_local_folder
from pioreactor.plugin_management.utils import get_package_plugin_display_name
from pioreactor.plugin_management.utils import get_python_plugin_file_display_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def uninstall_plugin(name_of_plugin: str) -> None:
    from pioreactor.logging import create_logger

    logger = create_logger("uninstall_plugin", experiment=UNIVERSAL_EXPERIMENT)
    # is it a local plugin file?
    local_plugin_file = next(
        (py_file for py_file in discover_plugins_in_local_folder() if py_file.stem == name_of_plugin), None
    )

    if local_plugin_file is not None:
        display_name = get_python_plugin_file_display_name(local_plugin_file)
        logger.debug(f"Uninstalling plugin `{display_name}`.")
        local_plugin_file.unlink()
        logger.notice(f"Successfully uninstalled plugin `{display_name}` from local plugins folder.")
        return

    # resolve before uninstalling, while the package metadata still exists.
    display_name = get_package_plugin_display_name(name_of_plugin)
    logger.debug(f"Uninstalling plugin `{display_name}`.")

    try:
        uninstall_plugin_assets(name_of_plugin, logger)
        result = uninstall_plugin_package(name_of_plugin)
    except Exception as exc:
        logger.error(f"Failed to uninstall plugin `{display_name}`.")
        logger.debug(str(exc))
        raise BashScriptError(f"Failed to uninstall plugin {name_of_plugin}.") from exc

    if "as it is not installed" in result.stderr:
        logger.warning(f"Unable to uninstall: plugin `{display_name}` is not installed.")
    elif result.returncode == 0:
        logger.notice(f"Successfully uninstalled plugin `{display_name}`.")
    else:
        logger.error(f"Failed to uninstall plugin `{display_name}`.")
        logger.debug(result.stdout)
        logger.debug(result.stderr)
        raise BashScriptError(f"Failed to uninstall plugin {name_of_plugin}.")

    return


@click.command(name="uninstall", short_help="uninstall an existing plugin")
@click.argument("name-of-plugin")
def click_uninstall_plugin(name_of_plugin: str) -> None:
    uninstall_plugin(name_of_plugin)
