# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from shlex import quote

import click

from pioreactor.logging import create_logger
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def uninstall_plugin(name_of_plugin):

    logger = create_logger("install_plugin", experiment=UNIVERSAL_EXPERIMENT)

    result = subprocess.run(
        [
            "bash",
            "/usr/local/bin/uninstall_pioreactor_plugin.sh",
            quote(name_of_plugin),
        ],
        capture_output=True,
    )

    if result.returncode == 0:
        logger.info(f"Successfully uninstalled plugin {name_of_plugin}.")
    else:
        logger.error(f"Failed to uninstall plugin {name_of_plugin}. See logs.")
        logger.debug(result.stdout)
        logger.debug(result.stderr)


@click.command(name="uninstall-plugin", short_help="uninstall an existing plugin")
@click.argument("name-of-plugin")
def click_uninstall_plugin(name_of_plugin):
    uninstall_plugin(name_of_plugin)
