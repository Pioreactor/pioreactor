#!/bin/bash

tail -q -f -n 0 /home/pi/.pm2/logs/ui-out.log /home/pi/.pm2/logs/ui-error.log  | sed -u '/^$/d' | jq -R -c --unbuffered '.|{message:., task: null, level: "DEBUG"}' | mosquitto_pub -l -t "pioreactor/$(hostname)/\$experiment/logs/ui"
