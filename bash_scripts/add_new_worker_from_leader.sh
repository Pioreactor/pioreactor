#!/bin/bash
# first argument is the new hostname of the pioreactor, to replace raspberry pi
# (optional) second argument is the new ip of the raspberry pi machine to replace.

set -x
export LC_ALL=C

MACHINE=${2:-"raspberrypi.local"}

# remove from known_hosts if already present
ssh-keygen -R $1.local                                                             >/dev/null 2>&1
ssh-keygen -R $1                                                                   >/dev/null 2>&1
ssh-keygen -R $MACHINE                                                             >/dev/null 2>&1
ssh-keygen -R $(host $MACHINE | awk '/has address/ { print $4 ; exit }')           >/dev/null 2>&1
ssh-keygen -R $(host $1 | awk '/has address/ { print $4 ; exit }')                 >/dev/null 2>&1


# allow us to SSH in, but make sure we can first before continuing.
while ! sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no $MACHINE "true"
    do echo "SSH to $MACHINE missed - `date`"
    sleep 3
done

sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no $MACHINE 'mkdir -p .ssh'
cat ~/.ssh/id_rsa.pub | sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no $MACHINE 'cat >> .ssh/authorized_keys'

# remove any existing config (for idempotent)
# we do this first so the user can see it on the Pioreactors/ page
rm -f /home/pi/.pioreactor/config_$1.ini
touch /home/pi/.pioreactor/config_$1.ini
echo -e "# Any settings here are specific to $1, and override the settings in shared config.ini" >> /home/pi/.pioreactor/config_$1.ini
crudini --set ~/.pioreactor/config.ini network.inventory $1 1

# install worker onto Rpi
ssh -o StrictHostKeyChecking=no $MACHINE "wget -O install_pioreactor_as_worker.sh https://gist.githubusercontent.com/CamDavidsonPilon/08aa165a283fb7af7262e4cb598bf6a9/raw/install_pioreactor_as_worker.sh && bash ./install_pioreactor_as_worker.sh $1"



# more needs to happen after the worker is online again (it reboots)
while ! ping -c1 $1 &>/dev/null
    do echo "Ping to $1 missed - `date`"
    sleep 2
done
echo "Host $1 found - `date`"
sleep 1


# remove from known_hosts if already present idk...
ssh-keygen -R $1                                                     >/dev/null 2>&1
ssh-keygen -R $(host $1 | awk '/has address/ { print $4 ; exit }')   >/dev/null 2>&1

# add to known hosts
ssh-keyscan -H $1 >> ~/.ssh/known_hosts

# sync-configs
pios sync-configs --units $1

# doesn't work
# cat /etc/timezone | ssh -o StrictHostKeyChecking=no $1 'cat >> sudo timedatectl set-timezone'

# reboot once more (previous reboot didn't have config.inis)
ssh -o StrictHostKeyChecking=no $1 'sudo reboot'

exit 0
