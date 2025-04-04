#!/bin/bash

set -xeu


export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER_HOSTNAME=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_hostname)
STORAGE_DIR=/home/pioreactor/.pioreactor/storage

# 1. create persistant db in all pioreactors
DB=$STORAGE_DIR/local_persistent_pioreactor_metadata.sqlite

if [ ! -f "$DB" ]; then
    touch $DB
    touch $DB-shm
    touch $DB-wal
fi

chown -R pioreactor:www-data $DB*
chmod -R 770 $DB*

# 2. make a calibration dir in all pioreactors
sudo -u pioreactor mkdir -p "$STORAGE_DIR"/calibrations/{od,media_pump,waste_pump,alt_media_pump}

# 3. install pyyaml (only leader has it, but workers need it now)
sudo pip3 install "$SCRIPT_DIR"/PyYAML-6.0.2-cp311-cp311-linux_armv7l.whl

# 4. update diskcache.sh
cp "$SCRIPT_DIR"/create_diskcache.sh /usr/local/bin/create_diskcache.sh
sudo bash /usr/local/bin/create_diskcache.sh

# 5. replace old calibrations with new yaml files. This doesn't delete old calibrations
sudo -u pioreactor python "$SCRIPT_DIR"/cal_convert.py "$STORAGE_DIR"/od_calibrations/cache.db
sudo -u pioreactor python "$SCRIPT_DIR"/cal_convert.py "$STORAGE_DIR"/pump_calibrations/cache.db
chown -R pioreactor:www-data "$STORAGE_DIR"/calibrations/

sudo -u pioreactor python "$SCRIPT_DIR"/cal_active.py "$STORAGE_DIR"/current_pump_calibration/cache.db
sudo -u pioreactor python "$SCRIPT_DIR"/cal_active.py "$STORAGE_DIR"/current_od_calibration/cache.db

# if leader
if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then

    # 6. remove calibrations dataset file
    rm -f /home/pioreactor/.pioreactor/exportable_datasets/*calibrations.yaml

    # 7. fix any bad pioreactor start up systemd services
    rm -f  /usr/lib/systemd/system/pioreactor_startup_run@.service
    cp  "$SCRIPT_DIR"/pioreactor_startup_run@.service /etc/systemd/system/


    # 8. add yaml mimetype
    echo "application/yaml               yaml yml" | sudo tee -a /etc/mime.types

    # 9. restart monitor and mqtt
    sudo systemctl daemon-reload
    sudo systemctl restart pioreactor_startup_run@monitor
    sudo systemctl restart pioreactor_startup_run@mqtt_to_db_streaming

fi
