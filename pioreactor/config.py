# -*- coding: utf-8 -*-

import configparser
import sys
import os


def get_config():
    config = configparser.ConfigParser()

    if "pytest" in sys.modules or os.environ.get("TESTING"):
        config.read("./config.dev.ini")
    else:
        global_config_path = "/home/pi/.pioreactor/config.ini"
        local_config_path = "/home/pi/.pioreactor/unit_config.ini"
        config.read([global_config_path, local_config_path])
    return config


config = get_config()


def get_leader_hostname():
    return config["network.topology"]["leader_hostname"]


def _config_bool(value):
    if value in ("0", "false", "False", "no", "off", "No", "NO", "Off", "OFF") or (
        not value
    ):
        return False
    return True


def get_active_workers_in_inventory():
    return [
        unit
        for (unit, available) in config["inventory"].items()
        if _config_bool(available)
    ]


leader_hostname = get_leader_hostname()
