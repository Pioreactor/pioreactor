# -*- coding: utf-8 -*-
import click
from pioreactor.exc import BashScriptError
from pioreactor.plugin_management.package_operations import install_plugin_assets
from pioreactor.plugin_management.package_operations import install_plugin_package
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def install_plugin(name_of_plugin: str, source: str | None = None) -> None:
    from pioreactor.logging import create_logger

    logger = create_logger("install_plugin", experiment=UNIVERSAL_EXPERIMENT)
    logger.debug(f"Installing plugin {name_of_plugin}.")

    try:
        plugin_was_installed = install_plugin_package(name_of_plugin, source)
        if not plugin_was_installed:
            logger.notice(f"Skipping LEADER_ONLY plugin {name_of_plugin} on worker.")
            return

        install_plugin_assets(name_of_plugin)
        logger.notice(f"Successfully installed plugin {name_of_plugin}.")
    except Exception as exc:
        logger.error(f"Failed to install plugin {name_of_plugin}. See logs.")
        logger.debug(str(exc))
        raise BashScriptError(f"Failed to install plugin {name_of_plugin}. See logs.") from exc


@click.command(name="install", short_help="install a plugin")
@click.argument("name-of-plugin")
@click.option(
    "--source",
    type=str,
    help="Install from a url, ex: https://github.com/user/repository/archive/branch.zip, or wheel file",
)
def click_install_plugin(name_of_plugin: str, source: str | None) -> None:
    install_plugin(name_of_plugin, source)
