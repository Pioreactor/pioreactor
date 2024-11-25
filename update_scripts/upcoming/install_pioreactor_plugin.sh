#!/bin/bash

# arg1 is the name of the plugin to install
# arg2 is the url, wheel, etc., possible None.
set -e
set -x
export LC_ALL=C

plugin_name=$1
source=$2

clean_plugin_name=${plugin_name,,} # lower cased

clean_plugin_name_with_dashes=${clean_plugin_name//_/-}
clean_plugin_name_with_underscores=${clean_plugin_name//-/_}
install_folder=$(python3 -c "import site; print(site.getsitepackages()[0])")/${clean_plugin_name_with_underscores}
leader_hostname=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)

if [ "$leader_hostname" = "$(hostname)" ]; then
  am_i_leader=true
else
  am_i_leader=false
fi


function download_and_check_if_leader_only {
    # define the package name
    local PACKAGE_NAME=$1
    # clean package name to match pip's conversion
    local CLEAN_PACKAGE_NAME=${PACKAGE_NAME//-/_}

    # Download the wheel file without dependencies
    pip download -qq --no-deps --dest /tmp $PACKAGE_NAME

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
    sudo pip3 install --force-reinstall "$source"
else
    if download_and_check_if_leader_only $clean_plugin_name_with_dashes; then
        if [ "$am_i_leader" = true ]; then
            echo "Not installing LEADER_ONLY plugin on worker"
            exit 0
        fi
        echo "Installing LEADER_ONLY plugin on worker"
    fi
    sudo pip3 install --upgrade --force-reinstall --ignore-installed "$clean_plugin_name_with_dashes"
fi




if [ "$am_i_leader" = true ]; then
    # merge new config.ini
    if test -f "$install_folder/additional_config.ini"; then
        crudini --merge /home/pioreactor/.pioreactor/config.ini < "$install_folder/additional_config.ini"
    fi

    # add any new sql, restart mqtt_to_db job, too
    if test -f "$install_folder/additional_sql.sql"; then
        sqlite3 "$(crudini --get /home/pioreactor/.pioreactor/config.ini storage database)" < "$install_folder/additional_sql.sql"
        sudo systemctl restart pioreactor_startup_run@mqtt_to_db_streaming.service
    fi

    # merge UI contribs
    if [ -d "$install_folder/ui/contrib/" ]; then
        rsync -a "$install_folder/ui/contrib/" /home/pioreactor/.pioreactor/plugins/ui/contrib/
    fi

    # merge datasets contribs
    if [ -d "$install_folder/exportable_datasets/" ]; then
        rsync -a "$install_folder/exportable_datasets/" /home/pioreactor/.pioreactor/plugins/exportable_datasets/
    fi

    # broadcast to cluster, don't crap out if we can't sync to a worker.
    pios sync-configs --shared || :
fi

# run a post install scripts.
if test -f "$install_folder/post_install.sh"; then
    bash "$install_folder/post_install.sh"
fi


exit 0
