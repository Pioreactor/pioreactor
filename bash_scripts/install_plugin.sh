#!/bin/bash

# arg1 is the name of the plugin to install
# arg2 is the version, possibly None
# arg3 is the git url, possible None.

plugin_name=$1
version=$2
url=$3

set +e

if [ ! -z $url ]
then
    sudo pip3 install $url
else
    sudo pip3 install -U $plugin_name
fi

plugin_name_with_underscores=${plugin_name//-/_}

crudini --merge /home/pi/.pioreactor/config.ini < /usr/local/lib/python3.7/dist-packages/$plugin_name_with_underscores/additional_config.ini
rsync -a /usr/local/lib/python3.7/dist-packages/$plugin_name_with_underscores/ui/contrib/ ~/pioreactorui/backend/contrib/
