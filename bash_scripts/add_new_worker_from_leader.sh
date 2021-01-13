#!/bin/bash

# first argument is the new name of the pioreactor, to replace raspberrypi

# remove from known_hosts if already present
ssh-keygen -R $1.local
ssh-keygen -R raspberrypi.local

# allow us to SSH in
sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no raspberrypi.local 'mkdir -p .ssh'
cat ~/.ssh/id_rsa.pub | sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no raspberrypi.local 'cat >> .ssh/authorized_keys'

# install worker onto Rpi
ssh -o StrictHostKeyChecking=no raspberrypi.local "wget -O install_pioreactor_as_worker.sh https://gist.githubusercontent.com/CamDavidsonPilon/08aa165a283fb7af7262e4cb598bf6a9/raw/install_pioreactor_as_worker.sh && bash ./install_pioreactor_as_worker.sh $1"

touch ~/.pioreactor/config_$1.ini
crudini --set ~/.pioreactor/config.ini inventory $1 1


# this needs to happen after the worker is online again (it reboots)

ssh $1
while test $? -gt 0
do
   sleep 3 # highly recommended - if it's in your local network, it can try an awful lot pretty quick...
   echo "Trying again..."
   ssh $1
done

# add to known hosts
ssh-keyscan -H $1 >> ~/.ssh/known_hosts
pios sync-configs
