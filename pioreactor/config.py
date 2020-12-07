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
    return config["topology"]["leader_hostname"]


def get_units_and_ips():
    return dict(
        [(unit, ip) for unit, ip in config["network"].items() if unit != "leader"]
    )


leader_hostname = get_leader_hostname()
