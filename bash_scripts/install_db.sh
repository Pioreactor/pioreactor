#!/bin/bash


# exit if any error
set -e
set -x
export LC_ALL=C


sudo apt-get install -y sqlite3
mkdir -p /home/pi/db
touch /home/pi/.pioreactor/pioreactor.sqlite
sqlite3 /home/pi/.pioreactor/pioreactor.sqlite < sql/sqlite_configuration.sql
sqlite3 /home/pi/.pioreactor/pioreactor.sqlite < sql/create_tables.sql

# attempt backup database every N days
# the below overwrites any existing crons
echo "0 0 */5 * * /usr/local/bin/pio run backup_database" | crontab -
