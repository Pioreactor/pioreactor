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

PIO_DIR=/home/pioreactor/.pioreactor


# the hostname of this system and the archive file should be the same. Exit if not.
if [ "$ARCHIVE_HOSTNAME" != "$CURRENT_HOSTNAME" ]; then
  echo "Error: Hostname of the archive does not match this hostname."
  exit 1
fi


# stop everything that might touch the database or config files...
pio kill --all-jobs > /dev/null
pio kill --job-name monitor
pio kill --job-name mqtt_to_db_streaming
sudo systemctl stop lighttpd.service || true
sudo systemctl stop huey.service || true

# blow away the old .pioreactor
rm -rf $PIO_DIR/

# create the new .pioreactor/
tar -xzf $ARCHIVE_NAME


leader_hostname=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$leader_hostname" = "$CURRENT_HOSTNAME" ]; then
  # rename the sqlite .backup, if leader
  mv $PIO_DIR/storage/pioreactor.sqlite.backup $PIO_DIR/storage/pioreactor.sqlite
  touch $PIO_DIR/storage/pioreactor.sqlite-shm
  touch $PIO_DIR/storage/pioreactor.sqlite-wal

  # check integrity, quickly
  DB_CHECK=$(sqlite3 $PIO_DIR/storage/pioreactor.sqlite "PRAGMA quick_check;")
  if [[ "$DB_CHECK" != "ok" ]]; then
      echo "Database integrity check failed: $DB_CHECK"
  fi

fi

# confirm permissions
chmod -R 770 $PIO_DIR/storage/
chown -R pioreactor:www-data $PIO_DIR/storage/
chmod g+s $PIO_DIR/storage/

echo "Done! Rebooting..."

sudo reboot
