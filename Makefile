install-python:
    sudo apt-get update & sudo apt install python3-pip
    sudo apt-get install python3-numpy
    pip3 install -r requirements.txt

install-mqtt:
    sudo apt install -y mosquitto mosquitto-clients
    sudo systemctl enable mosquitto.service

install: install-mqtt install-python
    echo "Finished installing"

measure:
    nohup python3 -m morbidostat.background_jobs.od_reading --od_angle_channel 135,0 --od_angle_channel 90,3 &
    nohup python3 -m morbidostat.background_jobs.growth_rate_calculating &
