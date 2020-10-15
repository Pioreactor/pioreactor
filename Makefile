install-python:
	sudo apt-get update & sudo apt install -y python3-pip
	sudo apt-get install -y python3-numpy
	pip3 install -r requirements.txt

install-mqtt:
	sudo apt install -y mosquitto mosquitto-clients
	sudo systemctl enable mosquitto.service

install-i2c:
	sudo apt-get install -y python-smbus
	sudo apt-get install -y i2c-tools
	echo "dtparam=i2c_arm=on"    | sudo tee /boot/config.txt -a
	echo "i2c-dev"               | sudo tee /etc/modules -a

install-worker: install-python install-mqtt configure-rpi systemd
	sudo python3 setup.py install

install-nodered:
	bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
	sudo systemctl enable nodered.service

install-db:
	sudo apt-get install -y sqlite3
	sqlite3 /home/pi/db/morbidostat.sqlite
	sqlite3 morbidostat.sqlite '.read sql/create_tables.sql'

systemd:
	cp /home/pi/morbidostat/startup/systemd/morbidostat.service /lib/systemd/system/morbidostat.service
	chmod 644 /lib/systemd/system/morbidostat.service
	sudo systemctl daemon-reload
	sudo systemctl enable morbidostat.service

configure-rpi:
	echo "gpu_mem=16"            | sudo tee /boot/config.txt -a
	echo "/usr/bin/tvservice -o" | sudo tee /etc/rc.local -a

install-leader: install-python install-mqtt configure-rpi install-db install-nodered
	pip3 install pandas
	sudo python3 setup.py install

view:
	ps x | grep python3

test:
	py.test -s
