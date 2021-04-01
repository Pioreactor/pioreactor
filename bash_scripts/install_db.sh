#!/bin/bash

# exit if any error
set -e


sudo apt-get install -y sqlite3
mkdir -p /home/pi/db
touch /home/pi/db/pioreactor.sqlite
sqlite3 /home/pi/db/pioreactor.sqlite < sql/sqlite_configuration.sql
sqlite3 /home/pi/db/pioreactor.sqlite < sql/create_tables.sql

# backup database every N hours
# this checks for duplicates in cron, too
crontab -l | grep 'backup_database' || (crontab -l 2>/dev/null; echo "0 0 * * * /usr/local/bin/pio run backup_database") | crontab -
