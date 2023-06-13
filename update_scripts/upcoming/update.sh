#!/bin/bash

set -x
set -e

export LC_ALL=C


# new naming for python install dirs/
wget -O /usr/local/bin/install_pioreactor_plugin.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/bash/install_pioreactor_plugin.sh
wget -O /usr/local/bin/uninstall_pioreactor_plugin.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/bash/uninstall_pioreactor_plugin.sh
