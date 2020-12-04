install-python:
	sudo apt-get update & sudo apt install -y python3-pip
	sudo apt-get install -y python3-numpy

install-mqtt:
	sudo apt install -y mosquitto mosquitto-clients
	sudo systemctl enable mosquitto.service

configure-mqtt-websockets:
	echo "listener 1883" | sudo tee /etc/mosquitto/mosquitto.conf -a
	echo "protocol mqtt" | sudo tee /etc/mosquitto/mosquitto.conf -a
	echo "listener 9001" | sudo tee /etc/mosquitto/mosquitto.conf -a
	echo "protocol websockets" | sudo tee /etc/mosquitto/mosquitto.conf -a

install-i2c:
	sudo apt-get install -y python-smbus
	sudo apt-get install -y i2c-tools
	echo "dtparam=i2c_arm=on"    | sudo tee /boot/config.txt -a
	echo "i2c-dev"               | sudo tee /etc/modules -a

systemd-worker:
	sudo cp /home/pi/pioreactor/startup/systemd/stirring.service /lib/systemd/system/stirring.service
	sudo cp /home/pi/pioreactor/startup/systemd/od_reading.service /lib/systemd/system/od_reading.service
	sudo cp /home/pi/pioreactor/startup/systemd/growth_rate_calculating.service /lib/systemd/system/growth_rate_calculating.service
	sudo chmod 644 /lib/systemd/system/stirring.service
	sudo chmod 644 /lib/systemd/system/growth_rate_calculating.service
	sudo chmod 644 /lib/systemd/system/od_reading.service

	sudo systemctl daemon-reload
	sudo systemctl enable od_reading.service
	sudo systemctl enable stirring.service
	sudo systemctl enable growth_rate_calculating.service

systemd-leader:
	sudo cp /home/pi/pioreactor/startup/systemd/ngrok.service /lib/systemd/system/ngrok.service
	sudo chmod 644 /lib/systemd/system/ngrok.service
	sudo systemctl enable ngrok.service

	sudo cp /home/pi/pioreactor/startup/systemd/time_series_aggregating.service /lib/systemd/system/time_series_aggregating.service
	sudo chmod 644 /lib/systemd/system/time_series_aggregating.service
	sudo systemctl enable time_series_aggregating.service

	sudo cp /home/pi/pioreactor/startup/systemd/log_aggregating.service /lib/systemd/system/log_aggregating.service
	sudo chmod 644 /lib/systemd/system/log_aggregating.service
	sudo systemctl enable log_aggregating.service

	sudo cp /home/pi/pioreactor/startup/systemd/mqtt_to_db_streaming.service /lib/systemd/system/mqtt_to_db_streaming.service
	sudo chmod 644 /lib/systemd/system/mqtt_to_db_streaming.service
	sudo systemctl enable mqtt_to_db_streaming.service

install-pioreactor-leader:
	sudo python3 setup.py install
	pip3 install -r requirements/requirements_leader.txt
	mkdir -p ~/.pioreactor
	cp config.ini ~/.pioreactor/config.ini

install-pioreactor-worker:
	sudo python3 setup.py install
	pip3 install -r requirements/requirements_worker.txt
	mkdir -p ~/.pioreactor
	touch ~/.pioreactor/unit_config.ini

install-db:
	sudo apt-get install -y sqlite3
	sqlite3 /home/pi/db/pioreactor.sqlite
	sqlite3 /home/pi/db/pioreactor.sqlite < sql/create_tables.sql

configure-rpi:
	echo "gpu_mem=16"            | sudo tee /boot/config.txt -a
	echo "/usr/bin/tvservice -o" | sudo tee /etc/rc.local -a


install-worker: install-python configure-rpi systemd-worker install-i2c install-pioreactor-worker

install-leader: install-python install-mqtt configure-mqtt-websockets configure-rpi install-db install-pioreactor-leader replace-config systemd-leader

test:
	py.test -s
