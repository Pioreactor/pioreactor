# -*- coding: utf-8 -*-

import configparser
import sys
import os


def get_config():
    config = configparser.ConfigParser()
    config.BOOLEAN_STATES = {
        **{k: False for k in ["0", "false", "no", "off"]},
        **{k: True for k in ["1", "yes", "true", "on"]},
    }

    if "pytest" in sys.modules or os.environ.get("TESTING"):
        config.read("./config.dev.ini")
    else:
        global_config_path = "/home/pi/.pioreactor/config.ini"
        local_config_path = "/home/pi/.pioreactor/unit_config.ini"
        config.read([global_config_path, local_config_path])
    return config


config = get_config()


def get_leader_hostname():
    return config.get("network.topology", "leader_hostname")


def get_active_workers_in_inventory():
    # because we are not using config.getbool here, values like "0" are seen as true,
    # hence we use the built in config.BOOLEAN_STATES to determine truthiness
    return [
        unit
        for (unit, available) in config["network.inventory"].items()
        if config.BOOLEAN_STATES[available]
    ]


leader_hostname = get_leader_hostname()
