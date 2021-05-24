# -*- coding: utf-8 -*-

import subprocess
import click


def install_plugin(self, name_of_plugin, version=None):

    subprocess.call(
        "/home/pi/pioreactor/bash_scripts/install_plugin.sh %s" % name_of_plugin,
        shell=True,
    )


@click.click()
def click_install_plugin(name_of_plugin, version):
    install_plugin(name_of_plugin, version)
