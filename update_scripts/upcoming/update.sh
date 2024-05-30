#!/bin/bash

set -xeu


export LC_ALL=C


echo "CONFIG_PATH=/home/pioreactor/.pioreactor/config.ini" >> /var/www/pioreactorui/.env || :
