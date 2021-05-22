#!/bin/bash

# first argument is the name of the plugin to install

set +e

sudo pip3 install $1
crudini --merge /home/pi/.pioreactor/config.ini < /usr/local/lib/python3.7/dist-packages/$1/additional_config.ini
rsync -a /usr/local/lib/python3.7/dist-packages/$1/ui/contrib/ ~/pioreactorui/backend/contrib/
