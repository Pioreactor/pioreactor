#!/bin/bash

set -xeu


export LC_ALL=C

# mv huey to correct folder, if it's wrong
sudo mv /lib/systemd/system/huey.service /etc/systemd/system/huey.service || :
# TODO: modify huey.service with the correct location
# TODO: modify 50-pioreactorui.conf with the correct location
# TODO: update update_ui.sh to also pip install the new package: sudo pip install --no-deps /var/www/pioreactorui/
