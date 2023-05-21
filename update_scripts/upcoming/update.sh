#!/bin/bash

set -x
set -e

export LC_ALL=C


# create experiment profile directories for users to add to
sudo mkdir /var/www/pioreactorui/contrib/experiment_profiles/
sudo chown pioreactor:www-data /var/www/pioreactorui/contrib/experiment_profiles/

sudo mkdir /home/pioreactor/.pioreactor/plugins/ui/contrib/experiment_profiles/
sudo chown pioreactor:pioreactor /home/pioreactor/.pioreactor/plugins/ui/contrib/experiment_profiles/
