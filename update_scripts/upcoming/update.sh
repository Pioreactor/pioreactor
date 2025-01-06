
sudo pip3 install FILE
mkdir ~/.pioreactor/storage/calibrations

replace create_dishcache.sh
TODO


# create persistant db

USERNAME=pioreactor
STORAGE_DIR=/home/$USERNAME/.pioreactor/storage
DB=$STORAGE_DIR/local_persistent_pioreactor_metadata.sqlite

touch $DB
touch $DB-shm
touch $DB-wal

chown -R $USERNAME:www-data $DB*