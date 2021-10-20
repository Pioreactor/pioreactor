#!/bin/bash

# arg1 is the name of the plugin to install
set -e
set -x
export LC_ALL=C

plugin_name=$1


sudo pip3 uninstall -y $plugin_name
