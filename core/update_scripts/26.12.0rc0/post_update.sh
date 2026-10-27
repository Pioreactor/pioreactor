#!/bin/bash

set -xeu

export LC_ALL=C

# Each unit now stores whether it's active, rather than asking the leader. Copy the leader's
# record (a no-op if this unit isn't in the inventory), so inactive units stay inactive. The
# leader's web server may be restarting during a cluster update, so retry for about a minute.
ACTIVE_ADOPTED=0
for _ in $(seq 1 12); do
    if sudo -u pioreactor -i pio active adopt; then
        ACTIVE_ADOPTED=1
        break
    fi
    sleep 5
done
if [ "$ACTIVE_ADOPTED" = 0 ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Unable to copy whether this unit is active from the leader. Run \`pio active adopt\` once the leader is reachable." || :
fi
