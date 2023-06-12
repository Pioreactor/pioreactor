# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from shlex import quote

import click

from pioreactor.logging import create_logger
from pioreactor.plugin_management.utils import discover_plugins_in_local_folder
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def uninstall_plugin(name_of_plugin: str) -> None:
    logger = create_logger("uninstall_plugin", experiment=UNIVERSAL_EXPERIMENT)
    logger.debug(f"Uninstalling plugin {name_of_plugin}.")

    # is it a local plugin file?
    for py_file in discover_plugins_in_local_folder():
        if py_file.stem == name_of_plugin:
            py_file.unlink()
            logger.notice(f"Successfully uninstalled plugin {name_of_plugin} from local plugins folder.")  # type: ignore
            return

    result = subprocess.run(
        [
            "bash",
            "/usr/local/bin/uninstall_pioreactor_plugin.sh",
            quote(name_of_plugin),
        ],
        capture_output=True,
    )
    if "as it is not installed" in result.stderr.decode("utf-8"):
        logger.warning(f"Unable to uninstall: plugin {name_of_plugin} is not installed.")
    elif result.returncode == 0:
        logger.notice(f"Successfully uninstalled plugin {name_of_plugin}.")  # type: ignore
    else:
        logger.error(f"Failed to uninstall plugin {name_of_plugin}. See logs.")
        logger.debug(result.stdout)
        logger.debug(result.stderr)

    return


@click.command(name="uninstall-plugin", short_help="uninstall an existing plugin")
@click.argument("name-of-plugin")
def click_uninstall_plugin(name_of_plugin: str) -> None:
    uninstall_plugin(name_of_plugin)
