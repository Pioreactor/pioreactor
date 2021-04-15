#!/bin/bash

# exit if any error
set -e


sudo apt-get install -y sqlite3
mkdir -p /home/pi/db
touch /home/pi/.pioreactor/pioreactor.sqlite
sqlite3 /home/pi/.pioreactor/pioreactor.sqlite < sql/sqlite_configuration.sql
sqlite3 /home/pi/.pioreactor/pioreactor.sqlite < sql/create_tables.sql

# backup database every N days
# this checks for duplicates in cron, too
crontab -l | grep 'backup_database' || (crontab -l 2>/dev/null; echo "0 0 */5 * * /usr/local/bin/pio run backup_database") | crontab -
