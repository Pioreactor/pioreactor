# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from shlex import quote

import click

from pioreactor.logging import create_logger
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def install_plugin(name_of_plugin, url=None):
    logger = create_logger("install_plugin", experiment=UNIVERSAL_EXPERIMENT)

    result = subprocess.run(
        [
            "bash",
            "/usr/local/bin/install_pioreactor_plugin.sh",
            quote(name_of_plugin),
            url or "",
        ],
        capture_output=True,
    )

    if result.returncode == 0:
        logger.info(f"Successfully installed plugin {name_of_plugin}.")
    else:
        logger.error(f"Failed to install plugin {name_of_plugin}. See logs.")
        logger.debug(result.stdout)
        logger.debug(result.stderr)


@click.command(name="install-plugin", short_help="install a plugin")
@click.argument("name-of-plugin")
@click.option(
    "--url",
    type=str,
    help="Install from a url, ex: https://github.com/user/repository/archive/branch.zip ",
)
def click_install_plugin(name_of_plugin, url):
    install_plugin(name_of_plugin, url)
