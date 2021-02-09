install-git:
	sudo apt update
	sudo apt install -y git

install-python:
	sudo apt install -y python3-pip
	# the following is needed for numpy on Rpi
	sudo apt-get install -y python3-numpy

install-mqtt:
	sudo apt install -y mosquitto mosquitto-clients
	sudo systemctl enable mosquitto.service

configure-mqtt-websockets:
	# append if not already present
	grep -qxF 'listener 1883' /etc/mosquitto/mosquitto.conf || echo "listener 1883" | sudo tee /etc/mosquitto/mosquitto.conf -a
	grep -qxF 'protocol mqtt' /etc/mosquitto/mosquitto.conf || echo "protocol mqtt" | sudo tee /etc/mosquitto/mosquitto.conf -a
	grep -qxF 'listener 9001' /etc/mosquitto/mosquitto.conf || echo "listener 9001" | sudo tee /etc/mosquitto/mosquitto.conf -a
	grep -qxF 'protocol websockets' /etc/mosquitto/mosquitto.conf || echo "protocol websockets" | sudo tee /etc/mosquitto/mosquitto.conf -a

install-i2c:
	sudo apt-get install -y python-smbus
	sudo apt-get install -y i2c-tools
	echo "dtparam=i2c_arm=on"    | sudo tee /boot/config.txt -a
	echo "i2c-dev"               | sudo tee /etc/modules -a

systemd-all:
	sudo cp /home/pi/pioreactor/startup/systemd/monitor_pioreactor.service /lib/systemd/system/monitor_pioreactor.service
	sudo chmod 644 /lib/systemd/system/monitor_pioreactor.service
	sudo systemctl enable monitor_pioreactor.service

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

	sudo cp /home/pi/pioreactor/startup/systemd/watchdog.service /lib/systemd/system/watchdog.service
	sudo chmod 644 /lib/systemd/system/watchdog.service
	sudo systemctl enable watchdog.service

	sudo cp /home/pi/pioreactor/startup/systemd/start_pioreactorui.service /lib/systemd/system/start_pioreactorui.service
	sudo chmod 644 /lib/systemd/system/start_pioreactorui.service
	sudo systemctl enable start_pioreactorui.service

	sudo cp /home/pi/pioreactor/startup/systemd/avahi-alias@.service /lib/systemd/system/avahi-alias@.service
	sudo chmod 644 /lib/systemd/system/avahi-alias@.service
	sudo systemctl enable avahi-alias@pioreactor.local.service

install-pioreactor-leader:
	sudo pip3 install -r /home/pi/pioreactor/requirements/requirements_leader.txt
	mkdir -p /home/pi/.pioreactor
	cp config.example.ini /home/pi/.pioreactor/config.ini
	sudo python3 setup.py install

	sudo pip3 install crudini
	crudini --set ~/.pioreactor/config.ini network.topology leader_hostname $$(hostname)
	crudini --set ~/.pioreactor/config.ini network.topology leader_address $$(hostname).local

	# the below will remove swap, which should help extend the life of SD cards:
	# https://raspberrypi.stackexchange.com/questions/169/how-can-i-extend-the-life-of-my-sd-card
	sudo apt-get remove dphys-swapfile -y

install-pioreactor-worker:
	sudo pip3 install -r /home/pi/pioreactor/requirements/requirements_worker.txt
	mkdir -p /home/pi/.pioreactor
	touch /home/pi/.pioreactor/unit_config.ini
	sudo python3 setup.py install

logging-files:
	sudo touch /var/log/pioreactor.log
	sudo chown pi /var/log/pioreactor.log

install-db:
	bash bash_scripts/install_db.sh

configure-rpi:
	# echo "gpu_mem=16"            | sudo tee /boot/config.txt -a
	# echo "/usr/bin/tvservice -o" | sudo tee /etc/rc.local -a
	sudo -upi mkdir -p /home/pi/.ssh

install-ui:
	# install NPM and Node
	wget -O - https://raw.githubusercontent.com/audstanley/NodeJs-Raspberry-Pi/master/Install-Node.sh | sudo bash

	# get latest pioreactorUI code from Github.
	# TODO: below is not idempotent
	git clone https://github.com/Pioreactor/pioreactorui.git /home/pi/pioreactorui  --depth 1
	# Use below to not have to use git
	# mkdir /home/pi/pioreactorui
	# curl -L https://api.github.com/repos/pioreactor/pioreactorui/tarball | tar -zxv -C /home/pi/pioreactorui --strip-components=1

	mv /home/pi/pioreactorui/backend/.env.example /home/pi/pioreactorui/backend/.env

	# install required libraries
	# npm --prefix /home/pi/pioreactorui/client install
	npm --prefix /home/pi/pioreactorui/backend install --loglevel verbose
	sudo npm install pm2@latest -g

	# we add another entry to mDNS: pioreactor.local, need the following:
	# see avahi-alias.service for how this works
	sudo apt-get install avahi-utils


configure-hostname:
	{ \
	set -e ;\
	if [ "$$(hostname)" = "raspberrypi" ]; then \
		read -p "Enter new Pioreactor name: " userEnteredPioName ;\
		sudo hostname $$userEnteredPioName ;\
		hostname | sudo tee /etc/hostname ;\
		sudo pip3 install pyhostman ;\
		sudo hostman remove --names raspberrypi ;\
		sudo hostman add 127.0.1.1 "$$(hostname)" ;\
	fi ;\
	}

configure-hostname-from-args:
	sudo hostname $(newHostname)
	hostname | sudo tee /etc/hostname
	sudo pip3 install pyhostman
	sudo hostman remove --names raspberrypi
	sudo hostman add 127.0.1.1 $(newHostname)

install-leader-as-worker: configure-hostname install-leader install-worker
	{ \
	set -e ;\
	touch /home/pi/.pioreactor/config_"$$(hostname)".ini ;\
	cat /home/pi/.ssh/id_rsa.pub > /home/pi/.ssh/authorized_keys ;\
	ssh-keyscan -H $$(hostname) >> /home/pi/.ssh/known_hosts ;\
	}
	crudini --set ~/.pioreactor/config.ini inventory $$(hostname) 1
	sudo reboot

seed-experiment:
	# not idempotent
	# techdebt: seed.sql adds an experiment to the db, so we need to match it in mqtt too
	sqlite3 /home/pi/db/pioreactor.sqlite < /home/pi/pioreactor/sql/seed.sql
	mosquitto_pub -t "pioreactor/latest_experiment" -m "Demo experiment" -r

install-worker: install-git install-python configure-hostname configure-rpi systemd-all systemd-worker install-i2c install-pioreactor-worker logging-files

install-worker-from-args: install-git install-python configure-hostname-from-args configure-rpi systemd-all systemd-worker install-i2c install-pioreactor-worker logging-files
	sudo reboot

install-leader: install-git install-python configure-hostname install-mqtt configure-mqtt-websockets configure-rpi install-db install-pioreactor-leader systemd-all systemd-leader logging-files install-ui seed-experiment
	# TODO: below is not idempotent
	ssh-keygen -q -t rsa -N '' -f /home/pi/.ssh/id_rsa
	sudo apt-get install sshpass
