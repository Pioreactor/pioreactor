#!/bin/bash

tail -q -f -n 0 /home/pi/.pm2/logs/ui-out.log /home/pi/.pm2/logs/ui-error.log  | sed -u -e 's/[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}T[0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}: /[PioreactorUI] /g' -e 'tx' -e 'd' -e ':x' | mosquitto_pub -l -t "pioreactor/$(hostname)/\$experiment/logs/ui"
