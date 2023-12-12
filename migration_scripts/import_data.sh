#!/bin/bash
# script to reimport data from a exported Pioreactor
# bash import_data.sh archive_name.zip

set -x
set -e

export LC_ALL=C


ARCHIVE_NAME=$1

# Extract the hostname from the archive name
ARCHIVE_HOSTNAME=$(echo "$ARCHIVE_NAME" | cut -d'_' -f 2)

# Get the current hostname of the system
CURRENT_HOSTNAME=$(hostname)

# the hostname of this system and the archive file should be the same. Exit if not.
if [ "$ARCHIVE_HOSTNAME" != "$CURRENT_HOSTNAME" ]; then
  echo "Error: Hostname of the archive does not match this hostname."
  exit 1
fi


# stop everything that might touch the database or config files...
pio kill --all-jobs > /dev/null
pio kill monitor watchdog mqtt_to_db_streaming
sudo systemctl stop lighttpd.service || true
sudo systemctl stop huey.service || true

# blow away the old .pioreactor
rm -rf /home/pioreactor/.pioreactor/

# create the new .pioreactor/
tar -xzf $ARCHIVE_NAME

# rename the sqlite .backup
mv /home/pioreactor/.pioreactor/storage/pioreactor.sqlite.backup /home/pioreactor/.pioreactor/storage/pioreactor.sqlite
touch /home/pioreactor/.pioreactor/storage/pioreactor.sqlite-shm
touch /home/pioreactor/.pioreactor/storage/pioreactor.sqlite-wal

# check integrity, quickly
DB_CHECK=$(sqlite3 /home/pioreactor/.pioreactor/storage/pioreactor.sqlite "PRAGMA quick_check;")
if [[ "$DB_CHECK" != "ok" ]]; then
    echo "Database integrity check failed: $DB_CHECK"
    exit 1
fi

# confirm permissions
chmod -R 770 /home/pioreactor/.pioreactor/storage/
chown -R pioreactor:www-data /home/pioreactor/.pioreactor/storage/
chmod g+s /home/pioreactor/.pioreactor/storage/

echo "Done! Rebooting..."

sudo reboot
