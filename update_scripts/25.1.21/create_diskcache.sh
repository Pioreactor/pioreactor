#!/bin/bash

set -x
set -e

export LC_ALL=C

DIR=/tmp/pioreactor_cache

mkdir -p $DIR

chmod -R 770 $DIR/
chown -R pioreactor:www-data $DIR/
chmod g+s $DIR


touch $DIR/huey.db
touch $DIR/huey.db-shm
touch $DIR/huey.db-wal


touch $DIR/local_intermittent_pioreactor_metadata.sqlite
touch $DIR/local_intermittent_pioreactor_metadata.sqlite-shm
touch $DIR/local_intermittent_pioreactor_metadata.sqlite-wal


chmod -R 770 $DIR/
