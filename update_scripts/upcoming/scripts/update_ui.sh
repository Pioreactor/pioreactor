#!/bin/bash
set -x
set -e

export LC_ALL=C

SRC_TAR=$1
TEMP_DIR=$(mktemp -d -t "pioreactorui_XXXX")
UI_FOLDER=/var/www/pioreactorui

function finish {
    # cleanup
    rm -rf "$TEMP_DIR" || true
    sudo systemctl restart lighttpd.service
    sudo systemctl restart huey.service
}
trap finish EXIT


# unpack source provided
tar -xzf "$SRC_TAR" -C $TEMP_DIR
WORK_DIR=$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d) # get the directory inside the archive, name is not predictable.

echo $WORK_DIR
# Verify that WORK_DIR is valid
if [[ -z "$WORK_DIR" ]]; then
    echo "Failed to find the working directory inside TEMP_DIR"
    exit 1
fi

# copy data over
# use rsync because we want to merge custom yamls the user has, we any updates to our own yamls.
rsync -ap --ignore-existing $UI_FOLDER/contrib/ $WORK_DIR/contrib/ 2>/dev/null || :

if [ -f "$UI_FOLDER/.env" ]; then
    echo "Copying .env file"
    cp -p $UI_FOLDER/.env $WORK_DIR
else
    echo ".env file does not exist in $UI_FOLDER"
fi

# swap folders
rm -rf $UI_FOLDER
mkdir $UI_FOLDER
cp -rp $WORK_DIR/. $UI_FOLDER
chgrp -R www-data $UI_FOLDER

ENV=$UI_FOLDER/.env
if [ -f "$ENV" ]; then
    echo "$ENV exists."
else
    mv $UI_FOLDER/.env.example $ENV
fi
