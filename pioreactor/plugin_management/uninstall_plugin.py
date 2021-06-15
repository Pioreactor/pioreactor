# -*- coding: utf-8 -*-

import subprocess
import click
from pioreactor.logging import create_logger
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def uninstall_plugin(name_of_plugin):

    logger = create_logger("install_plugin", experiment=UNIVERSAL_EXPERIMENT)

    result = subprocess.call(
        ["bash", "/home/pi/pioreactor/bash_scripts/uninstall_plugin.sh", name_of_plugin]
    )

    if result == 0:
        logger.info(f"Successfully uninstalled plugin {name_of_plugin}.")
    else:
        logger.error(f"Failed to uninstall plugin {name_of_plugin}. See logs.")


@click.command(name="uninstall-plugin", short_help="uninstall an existing plugin")
@click.argument("name-of-plugin")
def click_uninstall_plugin(name_of_plugin):
    uninstall_plugin(name_of_plugin)
