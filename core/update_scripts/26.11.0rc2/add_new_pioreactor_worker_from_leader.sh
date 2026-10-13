#!/bin/bash
# Set up SSH from the leader to a new worker, so the leader can configure it.
# `pio workers add` runs this, then copies config.ini over and runs `pio join-cluster` on the worker.
# first argument is the hostname of the new pioreactor worker
# second argument is the worker address
# the worker password is read from $SSHPASS, default "raspberry"

set -e
export LC_ALL=C

HOSTNAME=$1
ADDRESS=$2
export SSHPASS=${SSHPASS:-raspberry}

# remove from known_hosts if already present
ssh-keygen -R "$ADDRESS"          >/dev/null 2>&1 || true
ssh-keygen -R "$HOSTNAME"                >/dev/null 2>&1 || true
ssh-keygen -R "$(getent hosts "$ADDRESS" | cut -d' ' -f1)"                 >/dev/null 2>&1 || true


# The leader already reached port 22, so this waits only for sshd and the filesystem.
# check we have .pioreactor folder to confirm the device has the pioreactor image
N=30
counter=0

while true
do
    STATUS=0
    sshpass -e ssh -o ConnectTimeout=5 pioreactor@"$ADDRESS" "test -d /home/pioreactor/.pioreactor" || STATUS=$?
    if [ "$STATUS" -eq 0 ]; then
        break
    fi

    # sshpass exits with 5 when the password is rejected.
    if [ "$STATUS" -eq 5 ]; then
        echo "Wrong password provided." >&2
        exit 1
    fi

    echo "Connection to $ADDRESS missed - $(date)" >&2
    counter=$((counter + 1))

    if [ "$counter" -eq "$N" ]; then
        echo "Attempted to connect $N times, but failed." >&2
        exit 1
    fi

    sleep 1
done


# Verify exact hostname match
ACTUAL_HOSTNAME=$(sshpass -e ssh pioreactor@"$ADDRESS" "hostname")
if [ "$ACTUAL_HOSTNAME" != "$HOSTNAME" ]; then
    echo "Hostname mismatch: expected '$HOSTNAME', but got '$ACTUAL_HOSTNAME'." >&2
    exit 1
fi

# copy public key over
sshpass -e ssh-copy-id pioreactor@"$ADDRESS" >&2

# add worker to known hosts on leader
ssh-keyscan "$ADDRESS" >> "/home/pioreactor/.ssh/known_hosts" 2>/dev/null
