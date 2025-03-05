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
PIO_VERSION=${3:-"1.1"}
PIO_MODEL=${4:-pioreactor_20ml}
ADDRESS=${5:-"$HOSTNAME".local}

USERNAME=pioreactor

LEADER_ADDRESS=$(crudini --get /home/$USERNAME/.pioreactor/config.ini cluster.topology leader_address)


# remove from known_hosts if already present
ssh-keygen -R "$ADDRESS"          >/dev/null 2>&1
ssh-keygen -R "$HOSTNAME"                >/dev/null 2>&1
ssh-keygen -R "$(getent hosts "$ADDRESS" | cut -d' ' -f1)"                 >/dev/null 2>&1


# allow us to SSH in, but make sure we can first before continuing.
# check we have .pioreactor folder to confirm the device has the pioreactor image
N=120
counter=0

while ! sshpass -p "$SSHPASS" ssh "$USERNAME"@"$ADDRESS" "test -d /home/$USERNAME/.pioreactor && echo 'exists'"
do
    echo "Connection to $ADDRESS missed - $(date)"

    if sshpass -v -p "$SSHPASS" ssh "$USERNAME"@"$ADDRESS"  |& grep "Wrong password"; then
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
ACTUAL_HOSTNAME=$(sshpass -p "$SSHPASS" ssh "$USERNAME"@"$ADDRESS" "hostname")
if [ "$ACTUAL_HOSTNAME" != "$HOSTNAME" ]; then
    echo "Hostname mismatch: expected '$HOSTNAME', but got '$ACTUAL_HOSTNAME'. Exiting."
    exit 1
fi

# copy public key over
sshpass -p "$SSHPASS" ssh-copy-id "$USERNAME"@"$ADDRESS"

# remove any existing config (for idempotent)
# we do this first so the user can see it on the Pioreactors/ page
UNIT_CONFIG=/home/$USERNAME/.pioreactor/config_"$HOSTNAME".ini

rm -f "$UNIT_CONFIG"
touch "$UNIT_CONFIG"
echo -e "# Any settings here are specific to $HOSTNAME, and override the settings in shared config.ini" >> "$UNIT_CONFIG"
crudini --set "$UNIT_CONFIG" pioreactor version "$PIO_VERSION" \
        --set "$UNIT_CONFIG" pioreactor model "$PIO_MODEL"

# add worker's address to config
CONFIG=/home/$USERNAME/.pioreactor/config.ini
crudini --set "$CONFIG" cluster.addresses "$HOSTNAME" "$ADDRESS"

# add worker to known hosts on leader
ssh-keyscan "$ADDRESS" >> "/home/$USERNAME/.ssh/known_hosts"


# sync-configs
pios sync-configs --units "$HOSTNAME" --skip-save
sleep 1

# check we have config.ini file to confirm the device has the necessary configuration
N=120
counter=0

while ! sshpass -p "$SSHPASS" ssh "$USERNAME"@"$ADDRESS" "test -f /home/$USERNAME/.pioreactor/config.ini && echo 'exists'"
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
ssh "$USERNAME"@"$ADDRESS" "sudo date --set \"$(date)\" && sudo fake-hwclock save"
ssh "$USERNAME"@"$ADDRESS" "echo \"server $LEADER_ADDRESS iburst prefer\" | sudo tee -a /etc/chrony/chrony.conf || :"


# reboot to set configuration
# the || true is because the connection fails, which returns as -1.
ssh "$USERNAME"@"$ADDRESS" 'sudo reboot;' || true

exit 0
