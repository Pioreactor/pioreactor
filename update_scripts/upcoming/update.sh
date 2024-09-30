#!/bin/bash

set -xeu


export LC_ALL=C

# mv huey to correct folder, if it's wrong
sudo mv /lib/systemd/system/huey.service /etc/systemd/system/huey.service || :
# TODO: modify huey.service with the correct location
