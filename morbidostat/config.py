# -*- coding: utf-8 -*-
# config.py
import os
import configparser
import sys


def get_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../config.ini")
    config.read(config_path)
    return config


def get_leader_hostname():
    if "pytest" in sys.modules:
        return "localhost"
    else:
        return get_config()["network"]["leader_hostname"]


leader_hostname = get_leader_hostname()
config = get_config()
