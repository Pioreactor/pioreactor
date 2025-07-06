#!/bin/bash

set -x
set -e

export LC_ALL=C

wget -O /usr/local/bin/install_pioreactor_plugin.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/a70a01c7f9736bbb43d126dbb1388722fe27b6a0/workspace/scripts/files/bash/install_pioreactor_plugin.sh
