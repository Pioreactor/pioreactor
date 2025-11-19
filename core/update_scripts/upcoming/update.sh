#!/bin/bash

set -xeu


export LC_ALL=C

# Changed Huey to use UMask=0002 so files/pip reinstalls stay readable to lighttpd while keeping group write intact

UNIT=/etc/systemd/system/huey.service
sudo sed -i 's/^UMask=.*/UMask=0002/' "$UNIT"
sudo systemctl daemon-reload

# but it's likely that the current pip install still has the wrong group, so force it this one time.
sudo chgrp -R www-data /opt/pioreactor/venv/lib/python3.13/site-packages/pioreactor
sudo chmod -R g+rX /opt/pioreactor/venv/lib/python3.13/site-packages/pioreactor
