# -*- coding: utf-8 -*-

import subprocess
import click


def uninstall_plugin(name_of_plugin):

    subprocess.call(
        ["bash", "/home/pi/pioreactor/bash_scripts/uninstall_plugin.sh", name_of_plugin]
    )


@click.command(name="uninstall-plugin", short_help="uninstall an existing plugin")
@click.argument("name-of-plugin")
def click_uninstall_plugin(name_of_plugin):
    uninstall_plugin(name_of_plugin)
