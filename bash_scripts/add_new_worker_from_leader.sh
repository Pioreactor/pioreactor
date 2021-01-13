#!/bin/bash

# first argument is the new name of the pioreactor, to replace raspberrypi

# remove from known_hosts if already present
ssh-keygen -R $1.local
ssh-keygen -R $1
ssh-keygen -R raspberrypi.local
ssh-keygen -R $(host raspberrypi.local | awk '/has address/ { print $4 ; exit }')
ssh-keygen -R $(host $1 | awk '/has address/ { print $4 ; exit }')


# allow us to SSH in
sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no raspberrypi.local 'mkdir -p .ssh'
cat ~/.ssh/id_rsa.pub | sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no raspberrypi.local 'cat >> .ssh/authorized_keys'

# install worker onto Rpi
ssh -o StrictHostKeyChecking=no raspberrypi.local "wget -O install_pioreactor_as_worker.sh https://gist.githubusercontent.com/CamDavidsonPilon/08aa165a283fb7af7262e4cb598bf6a9/raw/install_pioreactor_as_worker.sh && bash ./install_pioreactor_as_worker.sh $1"

touch ~/.pioreactor/config_$1.ini
crudini --set ~/.pioreactor/config.ini inventory $1 1


# more needs to happen after the worker is online again (it reboots)
while ! ping -c1 $1 &>/dev/null
        do echo "Ping missed - `date`"
        sleep 2
done
echo "Host $1 found - `date`"
sleep 1


# remove from known_hosts if already present idk...
ssh-keygen -R $1
ssh-keygen -R $(host $1 | awk '/has address/ { print $4 ; exit }')

# add to known hosts
ssh-keyscan -H $1 >> ~/.ssh/known_hosts

# sync-configs
pios sync-configs --units $1
