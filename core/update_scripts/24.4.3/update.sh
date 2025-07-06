#!/bin/bash

set -x
set -e

export LC_ALL=C


#### update write_ip.sh

# Define the new script content
NEW_SCRIPT=$(cat <<'EOF'
#!/bin/bash

set -x
set -e

export LC_ALL=C

# Get the first IPv4 address
IP=$(hostname -I | awk '{print $1}')

# Check if the network interfaces exist and get their MAC addresses
if [ -d /sys/class/net/wlan0 ]; then
    WLAN_MAC=$(cat /sys/class/net/wlan0/address)
else
    WLAN_MAC="Not available"
fi

if [ -d /sys/class/net/eth0 ]; then
    ETH_MAC=$(cat /sys/class/net/eth0/address)
else
    ETH_MAC="Not available"
fi

# Write the information to a file in key-value format
echo "HOSTNAME=$(hostname)" >> /boot/firmware/network_info.txt
echo "IP=$IP" > /boot/firmware/network_info.txt
echo "WLAN_MAC=$WLAN_MAC" >> /boot/firmware/network_info.txt
echo "ETH_MAC=$ETH_MAC" >> /boot/firmware/network_info.txt

EOF
)

# Write the new script content to the file
sudo echo "$NEW_SCRIPT" > /usr/local/bin/write_ip.sh

# Make the new script executable
sudo chmod +x /usr/local/bin/write_ip.sh



#### LEADER only!

PIO_DIR=/home/pioreactor/.pioreactor
# Get the hostname
HOSTNAME=$(hostname)

# Get the leader address
LEADER_HOSTNAME=$(crudini --get $PIO_DIR/config.ini cluster.topology leader_hostname)

if [ "$HOSTNAME" = "$LEADER_HOSTNAME" ]; then


    #### Fix issue with `pio log` commands in systemd services failing

    # List of systemd files
    systemd_files=("/lib/systemd/system/avahi_aliases.service" "/lib/systemd/system/load_rp2040.service")

    # Loop through each file and add 'User=pioreactor' and 'EnvironmentFile=/etc/environment' under '[Service]' if they don't already exist
    for file in "${systemd_files[@]}"; do
        sudo crudini --ini-options=nospace --set "$file" Service User pioreactor \
                                      --set "$file" Service EnvironmentFile "/etc/environment"
    done

    sudo systemctl daemon-reload

    sudo systemctl restart avahi_aliases.service
    sudo systemctl restart load_rp2040.service



    ### update add_new_pioreactor_worker_from_leader to use `pio workers discover``

    FILE_PATH="/usr/local/bin/add_new_pioreactor_worker_from_leader.sh"
    sudo sed -i 's/pio discover-workers/pio workers discover/g' "$FILE_PATH"
fi
