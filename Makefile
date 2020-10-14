install-python:
	sudo apt-get update & sudo apt install -y python3-pip
	sudo apt-get install -y python3-numpy
	pip3 install -r requirements.txt

install-mqtt:
	sudo apt install -y mosquitto mosquitto-clients
	sudo systemctl enable mosquitto.service

install: install-python install-mqtt configure-rpi
	sudo python3 setup.py install

install-db:
	sudo apt-get install -y sqlite3
	sqlite3 /home/pi/db/morbidostat.sqlite
	sqlite3 morbidostat.sqlite '.read sql/create_tables.sql'

configure-rpi:
	echo "gpu_mem=16"            | sudo tee /boot/config.txt -a
	echo "dtparam=i2c_arm=on"    | sudo tee /boot/config.txt -a
	echo "i2c-dev"               | sudo tee /etc/modules -a
	echo "/usr/bin/tvservice -o" | sudo tee /etc/rc.local -a

install-leader: install install-db
	bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
	sudo systemctl enable nodered.service
	pip3 install pandas

view:
	ps x | grep python3

test:
	py.test -s
