#!/bin/bash

set -x
set -e

export LC_ALL=C

DIR=/tmp/pioreactor_cache

mkdir -p $DIR
chown -R pioreactor:www-data $DIR/
chmod g+s $DIR


touch $DIR/huey.db
touch $DIR/huey.db-shm
touch $DIR/huey.db-wal
