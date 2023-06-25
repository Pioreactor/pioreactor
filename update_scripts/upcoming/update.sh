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

# update OD calibrations, `inferred_od600s` is now `od600s`
sudo -u pioreactor python3 - << EOF
# -*- coding: utf-8 -*-
import json

from pioreactor.utils import local_persistant_storage
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def transform_cache(cache):
    for name in list(cache):
        cal = json.loads(cache[name])
        try:
            cal["od600s"] = cal["inferred_od600s"]
            cal.pop("inferred_od600s")
            cache[name] = json.dumps(cal, separators=(",", ":")).encode()
        except Exception as e:
            print(e)

# od600 calibrations
with local_persistant_storage("od_calibrations") as cache:
    transform_cache(cache)

with local_persistant_storage("current_od_calibration") as cache:
    transform_cache(cache)
EOF
