#!/bin/bash
# this script "connects" the leader to the worker.
# first argument is the name of the new/hostname pioreactor worker
# second optional argument is the worker password, default "raspberry"
# third optional argument is the Pioreactor version, default "1.1"
# forth optional argument is the Pioreactor model, default "pioreactor_20ml"
# fifth optional argument is the address of the new Pioreactor, default "<hostname>.local"

set -x
set -e
export LC_ALL=C

HOSTNAME=$1
SSHPASS=${2:-raspberry}
ADDRESS=${3:-"$HOSTNAME".local}


LEADER_ADDRESS=$(crudini --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_address)


# remove from known_hosts if already present
ssh-keygen -R "$ADDRESS"          >/dev/null 2>&1
ssh-keygen -R "$HOSTNAME"                >/dev/null 2>&1
ssh-keygen -R "$(getent hosts "$ADDRESS" | cut -d' ' -f1)"                 >/dev/null 2>&1


# allow us to SSH in, but make sure we can first before continuing.
# check we have .pioreactor folder to confirm the device has the pioreactor image
N=120
counter=0

while ! sshpass -p "$SSHPASS" ssh pioreactor@"$ADDRESS" "test -d /home/pioreactor/.pioreactor && echo 'exists'"
do
    echo "Connection to $ADDRESS missed - $(date)"

    if sshpass -v -p "$SSHPASS" ssh pioreactor@"$ADDRESS"  |& grep "Wrong password"; then
        echo "Wrong password provided."
    fi

    counter=$((counter + 1))

    if [ "$counter" -eq "$N" ]; then
        echo "Attempted to connect $N times, but failed. Exiting."
        exit 1
    fi

    sleep 1
done


# Verify exact hostname match
ACTUAL_HOSTNAME=$(sshpass -p "$SSHPASS" ssh pioreactor@"$ADDRESS" "hostname")
if [ "$ACTUAL_HOSTNAME" != "$HOSTNAME" ]; then
    echo "Hostname mismatch: expected '$HOSTNAME', but got '$ACTUAL_HOSTNAME'. Exiting."
    exit 1
fi

# copy public key over
sshpass -p "$SSHPASS" ssh-copy-id pioreactor@"$ADDRESS"

# remove any existing config (for idempotent)
# we do this first so the user can see it on the Pioreactors/ page
UNIT_CONFIG=/home/pioreactor/.pioreactor/config_"$HOSTNAME".ini

rm -f "$UNIT_CONFIG"
touch "$UNIT_CONFIG"
echo -e "# Any settings here are specific to $HOSTNAME, and override the settings in shared config.ini" >> "$UNIT_CONFIG"

# add worker's address to config
CONFIG=/home/pioreactor/.pioreactor/config.ini
crudini --set "$CONFIG" cluster.addresses "$HOSTNAME" "$ADDRESS"

# add worker to known hosts on leader
ssh-keyscan "$ADDRESS" >> "/home/pioreactor/.ssh/known_hosts"

# sync-configs - can't use pios sync-config since this isn't part of our cluster yet.
scp "$CONFIG" pioreactor@"$ADDRESS":/home/pioreactor/.pioreactor/config.ini
scp "$UNIT_CONFIG" pioreactor@"$ADDRESS":/home/pioreactor/.pioreactor/unit_config.ini

sleep 1

# check we have config.ini file to confirm the device has the necessary configuration
N=120
counter=0

while ! sshpass -p "$SSHPASS" ssh pioreactor@"$ADDRESS" "test -f /home/pioreactor/.pioreactor/config.ini && echo 'exists'"
do
    echo "Looking for config.ini - $(date)"

    counter=$((counter + 1))

    if [ "$counter" -eq "$N" ]; then
        echo "Attempted to find config.ini $N times, but failed. Exiting."
        exit 1
    fi

    sleep 1
done

# sync date & times, specifically for LAP see https://github.com/Pioreactor/pioreactor/issues/269
ssh pioreactor@"$ADDRESS" "sudo date --set \"$(date)\" && sudo fake-hwclock save"
ssh pioreactor@"$ADDRESS" "echo \"server $LEADER_ADDRESS iburst prefer\" | sudo tee -a /etc/chrony/chrony.conf || :"


# reboot to set configuration
# the || true is because the connection fails, which returns as -1.
ssh pioreactor@"$ADDRESS" 'sudo reboot;' || true

exit 0
