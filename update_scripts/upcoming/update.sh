#!/bin/bash

set -xeu


export LC_ALL=C


UI_FOLDER=/var/www/pioreactorui
SYSTEMD_DIR=/lib/systemd/system/
UI_TAG="TODO"

HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get "$PIO_DIR"/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then
    # worker updates

    # 1. install pioreactorui
    mkdir /var/www

    tar -xzf pioreactorui.tar.gz # TODO: correct location
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
    apt-get install lighttpd -y # TODO

    # install our own lighttpd service
    sudo cp /files/system/systemd/lighttpd.service $SYSTEMD_DIR
    sudo systemctl enable lighttpd.service


    cp /files/system/lighttpd/lighttpd.conf        /etc/lighttpd/lighttpd.conf
    cp /files/system/lighttpd/50-pioreactorui.conf /etc/lighttpd/conf-available/50-pioreactorui.conf
    cp /files/system/lighttpd/52-api-only.conf     /etc/lighttpd/conf-available/52-api-only.conf

    lighttpd-enable-mod fastcgi
    lighttpd-enable-mod rewrite
    lighttpd-enable-mod pioreactorui
    # workers only have an api, not served static files.
    lighttpd-enable-mod api-only


    # 2. Add necessary files and services
    # TODO: add update_ui.sh
    # TODO: add create_diskcache.sh
    # TODO: add huey.service
    # TODO: add create_diskcache.service


fi

# TODO add updated pioreactorui lighttpd conf
