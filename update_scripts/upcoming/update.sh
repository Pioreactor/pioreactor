#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

UI_FOLDER=/var/www/pioreactorui
SYSTEMD_DIR=/lib/systemd/system/
UI_TAG="TODO" # TODO
PIO_DIR="/home/pioreactor/.pioreactor"

HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get "$PIO_DIR"/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    # worker updates

    # install pioreactorui
    rm -rf $UI_FOLDER
    mkdir -p /var/www


    tar -xzf "$SCRIPT_DIR"/pioreactorui_"$UI_TAG".tar.gz
    mv pioreactorui-"$UI_TAG" /var/www
    mv /var/www/pioreactorui-"$UI_TAG" $UI_FOLDER

    # init .env
    mv $UI_FOLDER/.env.example $UI_FOLDER/.env

    # init sqlite db
    touch $UI_FOLDER/huey.db
    touch $UI_FOLDER/huey.db-shm
    touch $UI_FOLDER/huey.db-wal


    # make correct permissions in new www folders and files
    # https://superuser.com/questions/19318/how-can-i-give-write-access-of-a-folder-to-all-users-in-linux
    chown -R pioreactor:www-data /var/www
    chmod -R g+w /var/www
    find /var/www -type d -exec chmod 2775 {} \;
    find /var/www -type f -exec chmod ug+rw {} \;
    chmod +x $UI_FOLDER/main.fcgi

    # install lighttp and set up mods
    unzip "$SCRIPT_DIR"/lighttpd_packages.zip -d "$SCRIPT_DIR"/lighttpd_packages
    dpkg -i "$SCRIPT_DIR"/lighttpd_packages/*.deb

    # install our own lighttpd service
    cp -u "$SCRIPT_DIR"/lighttpd.service $SYSTEMD_DIR

    cp -u "$SCRIPT_DIR"/lighttpd.conf        /etc/lighttpd/
    cp -u "$SCRIPT_DIR"/50-pioreactorui.conf /etc/lighttpd/conf-available/
    cp -u "$SCRIPT_DIR"/52-api-only.conf     /etc/lighttpd/conf-available/

    /usr/sbin/lighttpd-enable-mod fastcgi
    /usr/sbin/lighttpd-enable-mod rewrite
    /usr/sbin/lighttpd-enable-mod pioreactorui
    # workers only have an api, not served static files.
    /usr/sbin/lighttpd-enable-mod api-only


    cp -u "$SCRIPT_DIR"/create_diskcache.sh /usr/local/bin/
    cp -u "$SCRIPT_DIR"/update_ui.sh        /usr/local/bin/

    cp -u "$SCRIPT_DIR"/huey.service $SYSTEMD_DIR
    cp -u "$SCRIPT_DIR"/create_diskcache.service $SYSTEMD_DIR

    # test new services
    huey_consumer -h
    lighttpd -h
    flask --help



    # we need to restart the monitor jobs on the worker so that the new table (pio_job_metadata) and db exist first
    systemctl restart pioreactor_startup_run@monitor.service
    sleep 5

    systemctl enable create_diskcache.service
    systemctl enable lighttpd.service
    systemctl enable huey.service

    systemctl start create_diskcache.service
    systemctl start lighttpd.service
    systemctl start huey.service

    sleep 1

    # test:
    curl -LI localhost/unit_api/jobs/running

else

    CONFIG_FILE=/etc/lighttpd/conf-available/50-pioreactorui.conf
    # add new unit_api to rewrite
    # Check if the unit_api rule is already present
    if grep -q 'unit_api' "$CONFIG_FILE"; then
      echo "unit_api rewrite rule already exists."
    else
      # Add the new rewrite rule for /unit_api
      sed -i '/^url.rewrite-once = (/a\  "^(/unit_api/.*)$" => "/main.fcgi$1",' "$CONFIG_FILE"
    fi

fi
