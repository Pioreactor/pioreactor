install-git:
	sudo apt update
	sudo apt install -y  git

install-python:
	sudo apt install -y python3-pip
	# the following is needed for numpy / pandas
	sudo apt install -y libatlas-base-dev

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

systemd-worker:
	sudo cp /home/pi/pioreactor/startup/systemd/stirring.service /lib/systemd/system/stirring.service
	sudo cp /home/pi/pioreactor/startup/systemd/od_reading.service /lib/systemd/system/od_reading.service
	sudo cp /home/pi/pioreactor/startup/systemd/growth_rate_calculating.service /lib/systemd/system/growth_rate_calculating.service
	sudo cp /home/pi/pioreactor/startup/systemd/monitor_pioreactor.service /lib/systemd/system/monitor_pioreactor.service

	sudo chmod 644 /lib/systemd/system/stirring.service
	sudo chmod 644 /lib/systemd/system/monitor_pioreactor.service
	sudo chmod 644 /lib/systemd/system/growth_rate_calculating.service
	sudo chmod 644 /lib/systemd/system/od_reading.service

	sudo systemctl daemon-reload
	sudo systemctl enable od_reading.service
	sudo systemctl enable monitor_pioreactor.service
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


install-pioreactor-leader:
	pip3 install -r requirements/requirements_leader.txt
	mkdir -p ~/.pioreactor
	cp config.ini ~/.pioreactor/config.ini
	sudo python3 setup.py install

install-pioreactor-worker:
	pip3 install -r requirements/requirements_worker.txt
	mkdir -p ~/.pioreactor
	touch ~/.pioreactor/unit_config.ini
	sudo python3 setup.py install

logging-files:
	sudo touch /var/log/pioreactor.log
	sudo chown pi /var/log/pioreactor.log

install-db:
	sudo apt-get install -y sqlite3
	mkdir -p /home/pi/db
	touch /home/pi/db/pioreactor.sqlite
	sqlite3 /home/pi/db/pioreactor.sqlite < sql/create_tables.sql

configure-rpi:
	echo "gpu_mem=16"            | sudo tee /boot/config.txt -a
	echo "/usr/bin/tvservice -o" | sudo tee /etc/rc.local -a


install-ui:
	# install NPM and Node
	wget -O - https://raw.githubusercontent.com/audstanley/NodeJs-Raspberry-Pi/master/Install-Node.sh | sudo bash

	# get latest pioreactorUI release from Github.
	git clone https://github.com/Pioreactor/pioreactorui.git /home/pi/pioreactorui  --depth 1
	# Use below to not have to use git
	# mkdir /home/pi/pioreactorui
	# curl -L https://api.github.com/repos/pioreactor/pioreactorui/tarball | tar -zxv -C /home/pi/pioreactorui --strip-components=1

	mv /home/pi/pioreactorui/backend/.env.example /home/pi/pioreactorui/backend/.env
	mkdir /home/pi/pioreactorui/backend/build/data/
	mkdir /home/pi/pioreactorui/backend/build/static/exports/

	# install required libraries
	# npm --prefix /home/pi/pioreactorui/client install
	npm --prefix /home/pi/pioreactorui/backend install
	sudo npm install pm2@latest -g

install-worker: configure-hostname install-git install-python configure-rpi systemd-worker install-i2c install-pioreactor-worker logging-files

install-leader: configure-hostname install-git install-python install-mqtt configure-mqtt-websockets configure-rpi install-db install-pioreactor-leader systemd-leader logging-files install-ui
	ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa
	sudo apt-get install sshpass

configure-hostname:
	if [ $$(hostname) = "raspberrypi" ]; then\
		read -p "Enter new Pioreactor name: " userEnteredPioName; \
		sudo hostname $$userEnteredPioName
		hostname | sudo tee /etc/hostname

		wget https://github.com/cbednarski/hostess/releases/download/v0.5.2/hostess_linux_arm
		chmod a+x hostess_linux_arm
		sudo ./hostess_linux_arm rm raspberrypi
		sudo ./hostess_linux_arm add "$$(hostname)" 127.0.1.1
	fi

install-leader-as-worker: configure-hostname install-leader install-worker
	# I had trouble with variables, quotes and dollar signs, so https://stackoverflow.com/questions/10121182/multiline-bash-commands-in-makefile/29085684#29085684
	{ \
	set -e ;\
	touch ~/.pioreactor/config_"$$(hostname)".ini ;\
	cat ~/.ssh/id_rsa.pub > ~/.ssh/authorized_keys ;\
	ssh-keyscan -H $$(hostname) >> ~/.ssh/known_hosts
	}
	sudo reboot
