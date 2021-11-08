#!/bin/bash


# exit if any error
set -e
set -x
export LC_ALL=C

DB_LOC=/home/pi/.pioreactor/storage/pioreactor.sqlite


sudo apt-get install -y sqlite3
mkdir -p /home/pi/db
touch $DB_LOC
sqlite3 $DB_LOC < sql/sqlite_configuration.sql
sqlite3 $DB_LOC < sql/create_tables.sql

# attempt backup database every N days
# the below overwrites any existing crons
echo "0 0 */5 * * /usr/local/bin/pio run backup_database" | crontab -
