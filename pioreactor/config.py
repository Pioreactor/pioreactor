# -*- coding: utf-8 -*-

import configparser
import sys
import os


def get_config():
    config = configparser.ConfigParser()

    if "pytest" in sys.modules or os.environ.get("TESTING"):
        config.read("config.dev.ini")
    else:
        global_config_path = "~/.pioreactor/config.ini"
        local_config_path = "~/.pioreactor/unit_config.ini"
        config.read([global_config_path, local_config_path])
    print(list(config))
    return config


def get_leader_hostname():
    return get_config()["network"]["leader_hostname"]


leader_hostname = get_leader_hostname()
config = get_config()
