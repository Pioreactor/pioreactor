#!/bin/bash

# arg1 is the name of the plugin to uninstall
set +e
set -x
export LC_ALL=C

plugin_name=$1

clean_plugin_name=${plugin_name,,} # lower cased

clean_plugin_name_with_dashes=${clean_plugin_name//_/-}
clean_plugin_name_with_underscores=${clean_plugin_name//-/_}
install_folder=$(python3 -c "import site; print(site.getsitepackages()[0])")/${clean_plugin_name_with_underscores}
leader_hostname=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)


# run a post install scripts.
if test -f "$install_folder/pre_uninstall.sh"; then
    bash "$install_folder/pre_uninstall.sh"
fi


if [ "$leader_hostname" == "$(hostname)" ]; then
    # delete yamls from ui
    (cd "$install_folder"/ui/contrib/ && find ./ -type f) | awk '{print "/home/pioreactor/.pioreactor/plugins/ui/contrib/"$1}' | xargs rm
    # delete yamls from datasets
    (cd "$install_folder"/exportable_datasets/ && find ./ -type f) | awk '{print "/home/pioreactor/.pioreactor/plugins/exportable_datasetss/"$1}' | xargs rm

    # TODO: remove sections from config.ini
    # this is complicated because sometimes we edit sections, instead of adding full sections. Ex: we edit [PWM] in relay plugin.
    # broadcast to cluster
    # pios sync-configs --shared
fi

sudo pip3 uninstall  -y "$clean_plugin_name_with_dashes"

exit 0
