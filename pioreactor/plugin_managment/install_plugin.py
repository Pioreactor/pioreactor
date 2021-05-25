# -*- coding: utf-8 -*-

import subprocess
import click


def install_plugin(self, name_of_plugin, version=None, url=None):

    subprocess.call(
        [
            "bash",
            "/home/pi/pioreactor/bash_scripts/install_plugin.sh",
            name_of_plugin,
            version or "",
            url or "",
        ]
    )


@click.command(name="install-plugin")
@click.argument("name-of-plugin")
@click.option(
    "--version",
    type=str,
    help="the version number of the package; leave empty for the latest version",
)
@click.option(
    "--url",
    type=str,
    help="Install from a url, ex: https://github.com/user/repository/archive/branch.zip ",
)
def click_install_plugin(name_of_plugin, version, url):
    install_plugin(name_of_plugin, version, url)
