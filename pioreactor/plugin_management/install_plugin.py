# -*- coding: utf-8 -*-

import subprocess
import click
from pioreactor.logging import create_logger
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def install_plugin(name_of_plugin, url=None):
    logger = create_logger("install_plugin", experiment=UNIVERSAL_EXPERIMENT)

    result = subprocess.call(
        [
            "bash",
            "/home/pi/pioreactor/bash_scripts/install_plugin.sh",
            name_of_plugin,
            url or "",
        ]
    ).returncode

    if result == 0:
        logger.info(f"Successfully installed plugin {name_of_plugin}.")
    else:
        logger.error(f"Failed to install plugin {name_of_plugin}.")


@click.command(name="install-plugin", short_help="install a plugin")
@click.argument("name-of-plugin")
@click.option(
    "--url",
    type=str,
    help="Install from a url, ex: https://github.com/user/repository/archive/branch.zip ",
)
def click_install_plugin(name_of_plugin, url):
    install_plugin(name_of_plugin, url)
