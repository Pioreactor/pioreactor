#!/bin/bash

# arg1 is the name of the plugin to install
# arg2 is the url, wheel, etc., possible None.
set -e
set -x
export LC_ALL=C

# Prefer Pioreactor venv if present
source /etc/pioreactor.env 2>/dev/null || true
VENV_BIN="${PIO_VENV:-/opt/pioreactor/venv}/bin"
PIP="$VENV_BIN/pip"
PY="$VENV_BIN/python"
CRUDINI="$VENV_BIN/crudini"

plugin_name=$1
source=$2

clean_plugin_name=${plugin_name,,} # lower cased

clean_plugin_name_with_dashes=${clean_plugin_name//_/-}
clean_plugin_name_with_underscores=${clean_plugin_name//-/_}
install_folder=$("$PY" -c "import site; print(site.getsitepackages()[0])")/${clean_plugin_name_with_underscores}
leader_hostname=$("$CRUDINI" --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

if [ "$leader_hostname" = "$(hostname)" ]; then
  am_i_leader=true
else
  am_i_leader=false
fi

ensure_dot_pioreactor_tree_group_is_www_data() {
    local base_dir="/home/pioreactor/.pioreactor"
    if [ -d "$base_dir" ]; then
        find "$base_dir" -mindepth 0 \( ! -user pioreactor -o ! -group www-data \) -exec chown -h pioreactor:www-data {} +
        chmod g+w "$base_dir"
        find "$base_dir" -mindepth 1 \( -type d -o -type f \) -exec chmod g+w {} +
        find "$base_dir" -type d ! -perm -2000 -exec chmod g+s {} +
    fi
}


function download_and_check_if_leader_only {
    # define the package name
    local PACKAGE_NAME=$1
    # clean package name to match pip's conversion
    local CLEAN_PACKAGE_NAME=${PACKAGE_NAME//-/_}

    # Download the wheel file without dependencies
    "$PIP" download -qq --no-deps --dest /tmp $PACKAGE_NAME

    # Get the file name of the downloaded package
    local WHL_FILE
    WHL_FILE=$(ls /tmp/$CLEAN_PACKAGE_NAME*.whl)

    # create a temp directory
    local TEMPDIR
    TEMPDIR=$(mktemp -d)

    # unzip the wheel file into temp directory
    unzip $WHL_FILE -d $TEMPDIR

    # check if LEADER_ONLY file exists
    if [ -f $TEMPDIR/LEADER_ONLY ]; then
        # if file exists, return 0 (true in bash)
        # remove the temp directory
        rm -rf $TEMPDIR
        rm  /tmp/$CLEAN_PACKAGE_NAME*.whl
        return 0
    else
        # if file does not exist, return 1 (false in bash)
        # remove the temp directory
        rm -rf $TEMPDIR
        rm  /tmp/$CLEAN_PACKAGE_NAME*.whl
        return 1
    fi

}



if [ -n "$source" ]; then
    sudo -u pioreactor "$PIP" install --force-reinstall --no-deps "$source"
else
    if download_and_check_if_leader_only "$clean_plugin_name_with_dashes"; then
        if [ "$am_i_leader" = false ]; then
            echo "Not installing LEADER_ONLY plugin on worker"
            exit 0
        fi
        echo "Installing LEADER_ONLY plugin on leader"
    fi
    sudo -u pioreactor "$PIP" install --upgrade --force-reinstall --ignore-installed "$clean_plugin_name_with_dashes"
fi


# merge UI contribs
if [ -d "$install_folder/ui/contrib/" ]; then
    # backwards compabitle
    rsync -a "$install_folder/ui/contrib/" /home/pioreactor/.pioreactor/plugins/ui/
elif [ -d "$install_folder/ui/" ]; then
    rsync -a "$install_folder/ui/" /home/pioreactor/.pioreactor/plugins/ui/
fi

# merge new config.ini
if test -f "$install_folder/additional_config.ini"; then
    "$CRUDINI" --merge /home/pioreactor/.pioreactor/unit_config.ini < "$install_folder/additional_config.ini"
fi


if [ "$am_i_leader" = true ]; then
    # add any new sql, restart mqtt_to_db job, too
    if test -f "$install_folder/additional_sql.sql"; then
        sqlite3 "$("$CRUDINI" --get /home/pioreactor/.pioreactor/config.ini storage database)" < "$install_folder/additional_sql.sql"
        sudo systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service
    fi

    # merge datasets contribs
    if [ -d "$install_folder/exportable_datasets/" ]; then
        rsync -a "$install_folder/exportable_datasets/" /home/pioreactor/.pioreactor/plugins/exportable_datasets/
    fi
fi

# run a post install scripts.
if test -f "$install_folder/post_install.sh"; then
    bash "$install_folder/post_install.sh"
fi

ensure_dot_pioreactor_tree_group_is_www_data


exit 0
