#!/bin/bash

# arg1 is the name of the plugin to uninstall
set +e
set -x
export LC_ALL=C

# Prefer Pioreactor venv if present
source /etc/pioreactor.env 2>/dev/null || true
VENV_BIN="${PIO_VENV:-/opt/pioreactor/venv}/bin"
PIP="$VENV_BIN/pip"
PY="$VENV_BIN/python"
CRUDINI="$VENV_BIN/crudini"

plugin_name=$1

clean_plugin_name=${plugin_name,,} # lower cased

clean_plugin_name_with_dashes=${clean_plugin_name//_/-}
clean_plugin_name_with_underscores=${clean_plugin_name//-/_}
install_folder=$("$PY" -c "import site; print(site.getsitepackages()[0])")/${clean_plugin_name_with_underscores}
leader_hostname=$("$CRUDINI" --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)


# run a post install script.
if test -f "$install_folder/pre_uninstall.sh"; then
    sudo bash "$install_folder/pre_uninstall.sh"
fi

# delete yamls from ui
(cd "$install_folder"/ui/ && find ./ -type f) | awk '{print "/home/pioreactor/.pioreactor/plugins/ui/"$1}' | xargs rm

if [ "$leader_hostname" == "$(hostname)" ]; then
    # delete yamls from datasets
    (cd "$install_folder"/exportable_datasets/ && find ./ -type f) | awk '{print "/home/pioreactor/.pioreactor/plugins/exportable_datasets/"$1}' | xargs rm

    # TODO: remove sections from config.ini
    # this is complicated because sometimes we edit sections, instead of adding full sections. Ex: we edit [PWM] in relay plugin.
    # broadcast to cluster
    # pios sync-configs --shared
fi

sudo -u pioreactor "$PIP" uninstall -y "$clean_plugin_name_with_dashes"

exit 0
