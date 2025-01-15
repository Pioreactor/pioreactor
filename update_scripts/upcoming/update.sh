#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get "$PIO_DIR"/config.ini cluster.topology leader_hostname)
USERNAME=pioreactor
STORAGE_DIR=/home/$USERNAME/.pioreactor/storage

# 1. create persistant db in all pioreactors
DB=$STORAGE_DIR/local_persistent_pioreactor_metadata.sqlite

if [ ! -f "$DB" ]; then
    touch $DB
    touch $DB-shm
    touch $DB-wal
fi

chown -R $USERNAME:www-data $DB*

# 2. make a calibration dir in all pioreactors
sudo -u $USERNAME mkdir -p "$STORAGE_DIR"/calibrations

# 3. install pyyaml (only leader has it, but workers need it now)
sudo pip3 install "$SCRIPT_DIR"/PyYAML-6.0.2-cp311-cp311-linux_armv7l.whl

# 4. update diskcache.sh
mv "$SCRIPT_DIR"/create_diskcache.sh /usr/local/bin/create_diskcache.sh

# 5. replace old calibrations with new yaml files. This doesn't delete old calibrations
python "$SCRIPT_DIR"/cal_convert.py "$STORAGE_DIR"/od_calibrations/cache.db
python "$SCRIPT_DIR"/cal_convert.py "$STORAGE_DIR"/pump_calibrations/cache.db

# if leader
if [ "$HOSTNAME" != "$LEADER_HOSTNAME" ]; then

    # 6. remove calibrations dataset file
    rm -f /home/pioreactor/.pioreactor/exportable_datasets/*calibrations.yaml


    # 7. fix any bad pioreactor start up systemd services
    rm -f  /usr/lib/systemd/system/pioreactor_startup_run@.service
    cp  "$SCRIPT_DIR"/pioreactor_startup_run@.service /etc/systemd/system/
    echo "application/yaml               yaml yml" | sudo tee -a /etc/mime.types

    # 8. add new config entries
    crudini  --set /home/pioreactor/.pioreactor/config.ini storage temporary_cache /tmp/pioreactor_cache/local_intermittent_pioreactor_metadata.sqlite \
             --set /home/pioreactor/.pioreactor/config.ini storage persistent_cache /home/pioreactor/.pioreactor/storage/local_persistent_pioreactor_metadata.sqlite

    sudo -u pioreactor pios sync-configs --shared || :


fi
