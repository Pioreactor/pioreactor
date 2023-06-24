#!/bin/bash

set -x
set -e

export LC_ALL=C

wget -O /usr/local/bin/install_pioreactor_plugin.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/bash/install_pioreactor_plugin.sh
wget -O /usr/local/bin/uninstall_pioreactor_plugin.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/bash/uninstall_pioreactor_plugin.sh

# adding bounds to the while loops
wget -O /usr/local/bin/add_new_pioreactor_worker_from_leader.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/bash/add_new_pioreactor_worker_from_leader.sh


# we write the IP address to /boot/ip
wget -O /usr/local/bin/everyboot.sh https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/bash/everyboot.sh
wget -O /lib/systemd/system/everyboot.service https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/system/systemd/everyboot.service
