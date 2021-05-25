# -*- coding: utf-8 -*-

import subprocess
import click


def install_plugin(self, name_of_plugin, url=None):

    subprocess.call(
        [
            "bash",
            "/home/pi/pioreactor/bash_scripts/install_plugin.sh",
            name_of_plugin,
            url or "",
        ]
    )


@click.command(name="install-plugin", short_help="install a plugin")
@click.argument("name-of-plugin")
@click.option(
    "--url",
    type=str,
    help="Install from a url, ex: https://github.com/user/repository/archive/branch.zip ",
)
def click_install_plugin(name_of_plugin, url):
    install_plugin(name_of_plugin, url)
