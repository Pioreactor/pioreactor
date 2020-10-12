install-python:
    sudo apt-get update & sudo apt install python3-pip
    sudo apt-get install python3-numpy
    pip3 install -r requirements.txt

install-mqtt:
    sudo apt install -y mosquitto mosquitto-clients
    sudo systemctl enable mosquitto.service

install: install-mqtt install-python
    sudo python3 setup.py install
    echo "Finished installing 👍"

install-leader: install
	bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
	sudo systemctl enable nodered.service
	pip3 install pandas

view:
    ps x | grep python3

test:
    py.test -s
