# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from shlex import quote

import click

from pioreactor.logging import create_logger
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def install_plugin(name_of_plugin: str, source: str | None = None) -> None:
    logger = create_logger("install_plugin", experiment=UNIVERSAL_EXPERIMENT)
    logger.debug(f"Installing plugin {name_of_plugin}.")
    command = [
        "bash",
        "/usr/local/bin/install_pioreactor_plugin.sh",
        quote(name_of_plugin),
        source or "",
    ]
    logger.debug(" ".join(command))

    result = subprocess.run(command, capture_output=True)

    if result.returncode == 0:
        logger.notice(f"Successfully installed plugin {name_of_plugin}.")  # type: ignore
    else:
        logger.error(f"Failed to install plugin {name_of_plugin}. See logs.")
        logger.debug(result.stdout)
        logger.debug(result.stderr)


@click.command(name="install-plugin", short_help="install a plugin")
@click.argument("name-of-plugin")
@click.option(
    "--source",
    type=str,
    help="Install from a url, ex: https://github.com/user/repository/archive/branch.zip, or wheel file",
)
def click_install_plugin(name_of_plugin: str, source: str | None):
    install_plugin(name_of_plugin, source)
