#!/bin/bash
# this script "connects" the leader to the worker.
# first argument is the name of the new/hostname pioreactor worker
# second optional argument is the worker password, default "raspberry"
# third optional argument is the Pioreactor version, default "1.1"

set -x
set -e
export LC_ALL=C

VENV_BIN="${PIO_VENV:-/opt/pioreactor/venv}/bin"
CRUDINI="$VENV_BIN/crudini"

HOSTNAME=$1
SSHPASS=${2:-raspberry}
ADDRESS=${3:-"$HOSTNAME".local}

LEADER_ADDRESS=$("$CRUDINI" --get /home/pioreactor/.pioreactor/config.ini cluster.topology leader_address)


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

# add worker's address to config
CONFIG=/home/pioreactor/.pioreactor/config.ini
"$CRUDINI" --set "$CONFIG" cluster.addresses "$HOSTNAME" "$ADDRESS"

# add worker to known hosts on leader
ssh-keyscan "$ADDRESS" >> "/home/pioreactor/.ssh/known_hosts"

# sync shared config.ini. The worker owns its own live unit_config.ini.
scp "$CONFIG" pioreactor@"$ADDRESS":/home/pioreactor/.pioreactor/config.ini

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
ssh pioreactor@"$ADDRESS" "sudo date --set \"$(date)\""
ssh pioreactor@"$ADDRESS" "echo \"server $LEADER_ADDRESS iburst prefer\" | sudo tee -a /etc/chrony/chrony.conf || :"


# reboot to set configuration
# the || true is because the connection fails, which returns as -1.
ssh pioreactor@"$ADDRESS" 'sudo reboot;' || true

exit 0
