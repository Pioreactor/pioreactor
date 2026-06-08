# -*- coding: utf-8 -*-
import click
from pioreactor.exc import BashScriptError
from pioreactor.plugin_management.package_operations import uninstall_plugin_assets
from pioreactor.plugin_management.package_operations import uninstall_plugin_package
from pioreactor.plugin_management.utils import discover_plugins_in_local_folder
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def uninstall_plugin(name_of_plugin: str) -> None:
    from pioreactor.logging import create_logger

    logger = create_logger("uninstall_plugin", experiment=UNIVERSAL_EXPERIMENT)
    logger.debug(f"Uninstalling plugin {name_of_plugin}.")

    # is it a local plugin file?
    for py_file in discover_plugins_in_local_folder():
        if py_file.stem == name_of_plugin:
            py_file.unlink()
            logger.notice(f"Successfully uninstalled plugin {name_of_plugin} from local plugins folder.")
            return

    try:
        uninstall_plugin_assets(name_of_plugin)
        result = uninstall_plugin_package(name_of_plugin)
    except Exception as exc:
        logger.error(f"Failed to uninstall plugin {name_of_plugin}. See logs.")
        logger.debug(str(exc))
        raise BashScriptError(f"Failed to uninstall plugin {name_of_plugin}. See logs.") from exc

    if "as it is not installed" in result.stderr:
        logger.warning(f"Unable to uninstall: plugin {name_of_plugin} is not installed.")
    elif result.returncode == 0:
        logger.notice(f"Successfully uninstalled plugin {name_of_plugin}.")
    else:
        logger.error(f"Failed to uninstall plugin {name_of_plugin}. See logs.")
        logger.debug(result.stdout)
        logger.debug(result.stderr)
        raise BashScriptError(f"Failed to uninstall plugin {name_of_plugin}. See logs.")

    return


@click.command(name="uninstall", short_help="uninstall an existing plugin")
@click.argument("name-of-plugin")
def click_uninstall_plugin(name_of_plugin: str) -> None:
    uninstall_plugin(name_of_plugin)
