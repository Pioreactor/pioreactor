#!/bin/bash

# first argument is the new name of the pioreactor, to replace raspberrypi

# remove from known_hosts if already present
ssh-keygen -R $1

# allow us to SSH in
sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no raspberrypi.local 'mkdir .ssh'
cat ~/.ssh/id_rsa.pub | sshpass -p 'raspberry' ssh -o StrictHostKeyChecking=no raspberrypi.local 'cat >> .ssh/authorized_keys'

# install worker onto Rpi
ssh -o StrictHostKeyChecking=no -o raspberrypi.local 'wget -O install_pioreactor_as_worker.sh https://gist.githubusercontent.com/CamDavidsonPilon/08aa165a283fb7af7262e4cb598bf6a9/raw/install_pioreactor_as_worker.sh && bash ./install_pioreactor_as_worker.sh $1'

# add to known hosts
ssh-keyscan -H $1 >> ~/.ssh/known_hosts

touch ~/.pioreactor/config_$1.ini

crudini --set ~/.pioreactor/config.ini inventory $1 1

pios sync-configs
