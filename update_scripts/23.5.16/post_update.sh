#!/bin/bash

set -x
set -e

export LC_ALL=C

# this is blocking systemd from complete and has to do with the pi username not having a password.
sudo systemctl stop userconfig.service
sudo systemctl disable userconfig.service
