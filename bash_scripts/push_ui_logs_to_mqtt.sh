#!/bin/bash

tail -q -f -n 0 /home/pi/.pm2/logs/ui-out.log /home/pi/.pm2/logs/ui-error.log  | jq -R -c --unbuffered '.[21:]|{message:., task: null, level: "DEBUG"}' | mosquitto_pub -l -t "pioreactor/$(hostname)/\$experiment/logs/ui"
