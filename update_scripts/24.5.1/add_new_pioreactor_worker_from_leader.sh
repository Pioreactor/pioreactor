#!/bin/bash
# this script "connects" the leader to the worker.
# first argument is the hostname of the new pioreactor worker
# second optional argument is the worker password, default "raspberry"
# third optional argument is the Pioreactor version, default "1.1"
# forth optional argument is the Pioreactor model, default "pioreactor_20ml"

set -x
set -e
export LC_ALL=C

SSHPASS=${2:-raspberry}
PIO_VERSION=${3:-"1.0"}
PIO_MODEL=${4:-pioreactor_20ml}

HOSTNAME=$1
HOSTNAME_local="$HOSTNAME".local

USERNAME=pioreactor

LEADER_HOSTNAME=$(hostname)


# remove from known_hosts if already present
ssh-keygen -R "$HOSTNAME_local"          >/dev/null 2>&1
ssh-keygen -R "$HOSTNAME"                >/dev/null 2>&1
ssh-keygen -R "$(getent hosts "$HOSTNAME_local" | cut -d' ' -f1)"                 >/dev/null 2>&1


# allow us to SSH in, but make sure we can first before continuing.
# check we have .pioreactor folder to confirm the device has the pioreactor image
N=120
counter=0

while ! sshpass -p "$SSHPASS" ssh "$USERNAME"@"$HOSTNAME_local" "test -d /home/$USERNAME/.pioreactor && echo 'exists'"
do
    echo "Connection to $HOSTNAME_local missed - $(date)"

    if sshpass -v -p "$SSHPASS" ssh "$USERNAME"@"$HOSTNAME_local"  |& grep "Wrong password"; then
        echo "Wrong password provided."
    fi

    counter=$((counter + 1))

    if [ "$counter" -eq "$N" ]; then
        echo "Attempted to connect $N times, but failed. Exiting."
        exit 1
    fi

    sleep 1
done

# check if it is a worker
if ! pio workers discover -t | grep -q "$HOSTNAME"; then
  echo "Unable to confirm if $HOSTNAME is a Pioreactor worker. Not found in 'pio workers discover -t'. Did you install the worker image?"
  exit 1
fi

# copy public key over
sshpass -p "$SSHPASS" ssh-copy-id "$USERNAME"@"$HOSTNAME_local"

# remove any existing config (for idempotent)
# we do this first so the user can see it on the Pioreactors/ page
UNIT_CONFIG=/home/$USERNAME/.pioreactor/config_"$HOSTNAME".ini
rm -f "$UNIT_CONFIG"
touch "$UNIT_CONFIG"
echo -e "# Any settings here are specific to $HOSTNAME, and override the settings in shared config.ini" >> "$UNIT_CONFIG"
crudini --set "$UNIT_CONFIG" pioreactor version "$PIO_VERSION" \
        --set "$UNIT_CONFIG" pioreactor model "$PIO_MODEL"

# add worker to known hosts on leader
ssh-keyscan "$HOSTNAME_local" >> "/home/$USERNAME/.ssh/known_hosts"

# sync-configs
pios sync-configs --units "$HOSTNAME" --skip-save
sleep 1

# check we have config.ini file to confirm the device has the necessary configuration
N=120
counter=0

while ! sshpass -p "$SSHPASS" ssh "$USERNAME"@"$HOSTNAME_local" "test -f /home/$USERNAME/.pioreactor/config.ini && echo 'exists'"
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
ssh "$USERNAME"@"$HOSTNAME_local" "echo \"server $LEADER_HOSTNAME.local iburst prefer\" | sudo tee -a  /etc/chrony/chrony.conf"


# reboot to set configuration
# the || true is because the connection fails, which returns as -1.
ssh "$USERNAME"@"$HOSTNAME_local" 'sudo reboot;' || true

exit 0
