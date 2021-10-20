#!/bin/bash

# arg1 is the name of the plugin to install
# arg2 is the git url, possible None.
set -e
set -x
export LC_ALL=C


plugin_name=$1
url=$2


if [ ! -z $url ]
then
    sudo pip3 install -I  $url
else
    sudo pip3 install -I $plugin_name
fi


# the below can fail, and will fail on a worker
set +e

plugin_name_with_underscores=${plugin_name//-/_}

crudini --merge /home/pi/.pioreactor/config.ini < /usr/local/lib/python3.7/dist-packages/$plugin_name_with_underscores/additional_config.ini
rsync -a /usr/local/lib/python3.7/dist-packages/$plugin_name_with_underscores/ui/contrib/ ~/pioreactorui/backend/contrib/


exit 0
