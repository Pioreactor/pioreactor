#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

UI_FOLDER=/var/www/pioreactorui
SYSTEMD_DIR=/etc/systemd/system/
UI_TAG="24.9.19" # TODO
PIO_DIR="/home/pioreactor/.pioreactor"

HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get "$PIO_DIR"/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    # worker updates

    # clean up from previous
    rm -rf $UI_FOLDER/*
    rm -rf /tmp/pioreactorui_cache/


    # install pioreactorui
    mkdir -p "$UI_FOLDER"
    tar -xzf "$SCRIPT_DIR"/pioreactorui_"$UI_TAG".tar.gz -C "$UI_FOLDER" --strip-components=1

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
    unzip -o "$SCRIPT_DIR"/lighttpd_packages.zip -d "$SCRIPT_DIR"/lighttpd_packages
    sudo chown -R pioreactor:pioreactor "$SCRIPT_DIR"/lighttpd_packages # required so this can be deleted by pioreactor user if needed to run again.
    dpkg -i "$SCRIPT_DIR"/lighttpd_packages/*.deb

    # install our own lighttpd service
    cp -u "$SCRIPT_DIR"/lighttpd.service $SYSTEMD_DIR

    cp -u "$SCRIPT_DIR"/lighttpd.conf        /etc/lighttpd/
    cp -u "$SCRIPT_DIR"/50-pioreactorui.conf /etc/lighttpd/conf-available/
    cp -u "$SCRIPT_DIR"/52-api-only.conf     /etc/lighttpd/conf-available/

    # lighttpd-enable-mod returns !0 if already enabled, breaking a potential reinstall.
    /usr/sbin/lighttpd-enable-mod fastcgi || true
    /usr/sbin/lighttpd-enable-mod rewrite || true
    /usr/sbin/lighttpd-enable-mod pioreactorui || true
    # workers only have an api, not served static files.
    /usr/sbin/lighttpd-enable-mod api-only || true


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
    sleep 1

    systemctl enable create_diskcache.service
    systemctl enable huey.service
    systemctl enable lighttpd.service

    systemctl start create_diskcache.service
    systemctl start huey.service
    systemctl start lighttpd.service

    sleep 2

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
