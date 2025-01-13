#!/bin/bash

set -x
set -e

export LC_ALL=C

DIR=/tmp/pioreactorui_cache

mkdir -p $DIR

touch $DIR/cache.db
touch $DIR/cache.db-shm
touch $DIR/cache.db-wal

touch $DIR/huey.db
touch $DIR/huey.db-shm
touch $DIR/huey.db-wal

chmod -R 770 $DIR/
chown -R pioreactor:www-data $DIR/
chmod g+s $DIR
