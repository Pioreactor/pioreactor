#!/bin/bash

# arg1 is the name of the plugin to install
set -e

plugin_name=$1


sudo pip3 uninstall -y $plugin_name
