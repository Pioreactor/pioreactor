#!/bin/bash
# this script "connects" the leader to the worker.
# first argument is the name of the new/hostname pioreactor worker
# second optional argument is the worker password, default "raspberry"
# third optional argument is the Pioreactor version, default "1.1"

set -x
set -e
export LC_ALL=C

# shellcheck source=/dev/null
source /etc/pioreactor.env 2>/dev/null || true
VENV_BIN="${PIO_VENV:-/opt/pioreactor/venv}/bin"
PIO="$VENV_BIN/pio"

HOSTNAME=$1
SSHPASS=${2:-raspberry}
ADDRESS=${3:-"$HOSTNAME".local}

LEADER_ADDRESS=$(sudo -u pioreactor "$PIO" config get cluster.topology leader_address --shared)


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

# A worker may still have topology overrides from a previous cluster. Since
# unit_config.ini overrides the shared config.ini, remove these values so this
# leader's shared configuration is authoritative.
ssh pioreactor@"$ADDRESS" '
    UNIT_CONFIG=/home/pioreactor/.pioreactor/unit_config.ini
    source /etc/pioreactor.env 2>/dev/null || true
    VENV_BIN="${PIO_VENV:-/opt/pioreactor/venv}/bin"

    if [ ! -f "$UNIT_CONFIG" ]; then
        exit 0
    fi

    if ! "$VENV_BIN/python" -c '\''import configparser, pathlib, sys; parser = configparser.ConfigParser(strict=False, allow_no_value=True); parser.read_string(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))'\'' "$UNIT_CONFIG"
    then
        echo "Unable to parse $UNIT_CONFIG. Fix its configuration before adding this worker." >&2
        exit 1
    fi

    for PARAMETER in leader_address leader_hostname
    do
        if VALUE=$("$VENV_BIN/crudini" --get "$UNIT_CONFIG" cluster.topology "$PARAMETER" 2>/dev/null); then
            echo "Removing [cluster.topology] $PARAMETER=$VALUE from worker unit_config.ini."
            "$VENV_BIN/crudini" --del "$UNIT_CONFIG" cluster.topology "$PARAMETER"
        fi
    done
'

# add worker's address to config
CONFIG=/home/pioreactor/.pioreactor/config.ini
sudo -u pioreactor "$PIO" config set cluster.addresses "$HOSTNAME" "$ADDRESS" --shared

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
# shellcheck disable=SC2029
ssh pioreactor@"$ADDRESS" "sudo date --set \"$(date)\""
# shellcheck disable=SC2029
ssh pioreactor@"$ADDRESS" "echo \"server $LEADER_ADDRESS iburst prefer\" | sudo tee -a /etc/chrony/chrony.conf || :"


# reboot to set configuration
# the || true is because the connection fails, which returns as -1.
ssh pioreactor@"$ADDRESS" 'sudo reboot;' || true

exit 0
