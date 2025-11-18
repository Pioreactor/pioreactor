#!/bin/bash

set -xeu


export LC_ALL=C

# Changed Huey to use UMask=0002 so files/pip reinstalls stay readable to lighttpd while keeping group write intact

UNIT=/etc/systemd/system/huey.service
sudo sed -i 's/^UMask=.*/UMask=0002/' "$UNIT"
sudo systemctl daemon-reload
