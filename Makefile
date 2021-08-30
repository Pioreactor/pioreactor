install-python:
	sudo apt update
	sudo apt install -y python3-pip

install-mqtt:
	sudo apt install -y mosquitto mosquitto-clients
	sudo systemctl enable mosquitto.service

configure-mqtt:
	# append if not already present
	grep -qxF 'autosave_interval 300' /etc/mosquitto/mosquitto.conf || echo "autosave_interval 300" | sudo tee /etc/mosquitto/mosquitto.conf -a
	grep -qxF 'listener 1883'         /etc/mosquitto/mosquitto.conf || echo "listener 1883"         | sudo tee /etc/mosquitto/mosquitto.conf -a
	grep -qxF 'protocol mqtt'         /etc/mosquitto/mosquitto.conf || echo "protocol mqtt"         | sudo tee /etc/mosquitto/mosquitto.conf -a
	grep -qxF 'listener 9001'         /etc/mosquitto/mosquitto.conf || echo "listener 9001"         | sudo tee /etc/mosquitto/mosquitto.conf -a
	grep -qxF 'protocol websockets'   /etc/mosquitto/mosquitto.conf || echo "protocol websockets"   | sudo tee /etc/mosquitto/mosquitto.conf -a

install-i2c:
	sudo apt install -y python-smbus # this is python2...
	sudo apt install -y i2c-tools
	echo "dtparam=i2c_arm=on"    | sudo tee /boot/config.txt -a
	echo "i2c-dev"               | sudo tee /etc/modules -a

systemd-all:
	sudo systemctl enable pioreactor_startup_run_always@monitor.service

systemd-worker:
	sudo cp /home/pi/pioreactor/system/systemd/pioreactor_startup_run_always@.service /lib/systemd/system/
	sudo cp /home/pi/pioreactor/system/systemd/pioreactor_startup_run@.service /lib/systemd/system/
	sudo systemctl daemon-reload

systemd-leader:
	sudo cp /home/pi/pioreactor/system/systemd/pioreactor_startup_run_always@.service /lib/systemd/system/
	sudo cp /home/pi/pioreactor/system/systemd/pioreactor_startup_run@.service /lib/systemd/system/

	sudo systemctl daemon-reload
	sudo systemctl enable pioreactor_startup_run_always@mqtt_to_db_streaming.service
	sudo systemctl enable pioreactor_startup_run_always@watchdog.service

	sudo cp /home/pi/pioreactor/system/systemd/start_pioreactorui.service /lib/systemd/system/
	sudo chmod 644 /lib/systemd/system/start_pioreactorui.service #TODO: why chmod?
	sudo systemctl enable start_pioreactorui.service

	sudo cp /home/pi/pioreactor/system/systemd/avahi-alias.service /lib/systemd/system/
	sudo chmod 644 /lib/systemd/system/avahi-alias.service
	sudo systemctl enable avahi-alias.service

	sudo cp /home/pi/pioreactor/system/systemd/timezone.service /lib/systemd/system/
	sudo chmod 644 /lib/systemd/system/timezone.service
	sudo systemctl enable timezone.service

install-pioreactor-leader:
	# the following is needed for numpy on Rpi
	sudo apt install -y python3-numpy

	sudo pip3 install -r /home/pi/pioreactor/requirements/requirements_leader.txt
	mkdir -p /home/pi/.pioreactor
	mkdir -p /home/pi/.pioreactor/local_storage
	cp /home/pi/pioreactor/config.example.ini /home/pi/.pioreactor/config.ini
	sudo python3 setup.py install

	# crudini is installed as part of requirements_leader.txt
	crudini --set ~/.pioreactor/config.ini network.topology leader_hostname $$(hostname)
	crudini --set ~/.pioreactor/config.ini network.topology leader_address $$(hostname).local

	# the below will remove swap, which should help extend the life of SD cards:
	# https://raspberrypi.stackexchange.com/questions/169/how-can-i-extend-the-life-of-my-sd-card
	sudo apt remove dphys-swapfile -y

install-log2ram:
	sudo echo "deb http://packages.azlux.fr/debian/ buster main" | sudo tee /etc/apt/sources.list.d/azlux.list
	sudo wget -qO - https://azlux.fr/repo.gpg.key | sudo apt-key add -
	# the below is need to recognize the additions above
	sudo apt update
	sudo apt install log2ram

install-pioreactor-worker:
	# the following is needed for numpy on Rpi
	sudo apt install -y python3-numpy

	sudo pip3 install -r /home/pi/pioreactor/requirements/requirements_worker.txt
	mkdir -p /home/pi/.pioreactor
	mkdir -p /home/pi/.pioreactor/local_storage
	touch /home/pi/.pioreactor/unit_config.ini
	sudo python3 setup.py install

logging-files:
	sudo touch /var/log/pioreactor.log
	sudo chown pi /var/log/pioreactor.log

	# add a logrotate entry
	sudo cp /home/pi/pioreactor/system/logrotate/pioreactor /etc/logrotate.d/pioreactor

install-db:
	bash /home/pi/pioreactor/bash_scripts/install_db.sh

configure-rpi:
	######################################################################
	# Optimize power consumption of Rpi - mostly turn off peripherals
	######################################################################

	# assign minimal memory to GPU
	echo "gpu_mem=16"            | sudo tee /boot/config.txt -a

	# disable bluetooth
	sudo systemctl disable hciuart
	echo "dtoverlay=disable-bt" | sudo tee -a /boot/config.txt

	# disable USB. This fails for the RPi Zero and A models, hence the starting "-"" to ignore error
	-echo '1-1' |sudo tee /sys/bus/usb/drivers/usb/unbind

	# disable HDMI
	# add to second line of script...
	sudo sed -i '2s/^/\/usr\/bin\/tvservice -o\n/' /etc/rc.local

	# remove activelow led - I think it's the red led
	echo "dtparam=act_led_activelow=on" | sudo tee -a /boot/config.txt

	#####################################################################
	#####################################################################

	sudo -upi mkdir -p /home/pi/.ssh

	# add hardware pwm
	echo "dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4" | sudo tee -a /boot/config.txt


install-ui:
	# install NPM and Node
	wget -O - https://raw.githubusercontent.com/audstanley/NodeJs-Raspberry-Pi/master/Install-Node.sh | sudo bash

	# get latest pioreactorUI code from Github.
	rm -rf /home/pi/pioreactorui
	git clone https://github.com/Pioreactor/pioreactorui.git /home/pi/pioreactorui  --depth 1
	# Use below to not have to use git
	# mkdir /home/pi/pioreactorui
	# curl -L https://api.github.com/repos/pioreactor/pioreactorui/tarball | tar -zxv -C /home/pi/pioreactorui --strip-components=1

	cp /home/pi/pioreactorui/backend/.env.example /home/pi/pioreactorui/backend/.env

	# install required libraries for backend
	npm --prefix /home/pi/pioreactorui/backend install
	sudo npm install pm2@5.1.0 -g

	# we add another entry to mDNS: pioreactor.local (can be modified in config.ini), and we need the following:
	# see avahi-alias.service for how this works
	sudo apt install avahi-utils -y


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
	-sudo hostman remove --names raspberrypi # the - is important: hostman returns a error if not found, we want to ignore it, hence use the ignore error flag. This makes this script idempotent.
	sudo hostman add -f 127.0.1.1 $(newHostname)

install-leader-as-worker: install-leader install-worker
	{ \
	set -e ;\
	touch /home/pi/.pioreactor/config_"$$(hostname)".ini ;\
	printf "# Any settings here are specific to $$(hostname), and override the settings in config.ini\n\n" >> /home/pi/.pioreactor/config_$$(hostname).ini ;\
	printf "[stirring]\n" >> /home/pi/.pioreactor/config_$$(hostname).ini   ;\
	printf "duty_cycle=80\n\n" >> /home/pi/.pioreactor/config_$$(hostname).ini  ;\
	printf "[pump_calibration]" >> /home/pi/.pioreactor/config_$$(hostname).ini  ;\
	cp /home/pi/.pioreactor/config_$$(hostname).ini /home/pi/.pioreactor/unit_config.ini ;\
	}

	crudini --set ~/.pioreactor/config.ini network.inventory $$(hostname) 1
	sudo reboot

seed-experiment:
	# techdebt: seed.sql adds an experiment to the db, so we need to match it in mqtt too
	sqlite3 /home/pi/.pioreactor/pioreactor.sqlite < /home/pi/pioreactor/sql/seed_initial_experiment.sql
	mosquitto_pub -t "pioreactor/latest_experiment" -m "Demo experiment" -r

install-worker: install-python configure-hostname configure-rpi systemd-worker systemd-all install-i2c install-pioreactor-worker logging-files install-log2ram
	sudo apt-get clean

install-worker-from-args: install-python configure-hostname-from-args configure-rpi systemd-worker systemd-all install-i2c install-pioreactor-worker logging-files
	sudo reboot

install-leader: install-python configure-hostname install-mqtt configure-mqtt configure-rpi install-pioreactor-leader install-db systemd-leader systemd-all logging-files install-ui seed-experiment
	sudo crudini --set /etc/log2ram.conf "" SIZE 75M

	rm -f /home/pi/.ssh/id_rsa
	ssh-keygen -q -t rsa -N '' -f /home/pi/.ssh/id_rsa
	sudo apt install sshpass
	cat /home/pi/.ssh/id_rsa.pub > /home/pi/.ssh/authorized_keys
	ssh-keyscan -H $$(hostname) >> /home/pi/.ssh/known_hosts

	sudo apt-get clean
