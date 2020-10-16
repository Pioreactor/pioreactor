install-python:
	sudo apt-get update & sudo apt install -y python3-pip
	sudo apt-get install -y python3-numpy

install-mqtt:
	sudo apt install -y mosquitto mosquitto-clients
	sudo systemctl enable mosquitto.service

install-i2c:
	sudo apt-get install -y python-smbus
	sudo apt-get install -y i2c-tools
	echo "dtparam=i2c_arm=on"    | sudo tee /boot/config.txt -a
	echo "i2c-dev"               | sudo tee /etc/modules -a

systemd:
	sudo cp /home/pi/morbidostat/startup/systemd/stirring.service /lib/systemd/system/stirring.service
	sudo cp /home/pi/morbidostat/startup/systemd/od_reading.service /lib/systemd/system/od_reading.service
	sudo cp /home/pi/morbidostat/startup/systemd/growth_rate_calculating.service /lib/systemd/system/growth_rate_calculating.service
	sudo chmod 644 /lib/systemd/system/stirring.service
	sudo chmod 644 /lib/systemd/system/growth_rate_calculating.service
	sudo chmod 644 /lib/systemd/system/od_reading.service

	sudo systemctl daemon-reload
	sudo systemctl enable od_reading.service
	sudo systemctl enable stirring.service
	sudo systemctl enable growth_rate_calculating.service

install-mobrbidostat:
	pip3 install -r requirements.txt
	sudo python3 setup.py install

install-worker: install-python install-mqtt configure-rpi systemd install-i2c install-mobrbidostat

install-db:
	sudo apt-get install -y sqlite3
	sqlite3 /home/pi/db/morbidostat.sqlite
	sqlite3 morbidostat.sqlite '.read sql/create_tables.sql'

install-nodered:
	bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
	sudo systemctl enable nodered.service

configure-rpi:
	echo "gpu_mem=16"            | sudo tee /boot/config.txt -a
	echo "/usr/bin/tvservice -o" | sudo tee /etc/rc.local -a

install-leader: install-python install-mqtt configure-rpi install-db install-nodered install-mobrbidostat
	pip3 install pandas

view:
	ps x | grep python3

test:
	py.test -s
