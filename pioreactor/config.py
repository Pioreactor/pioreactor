# -*- coding: utf-8 -*-

import configparser
import sys
import os
from functools import lru_cache


def __getattr__(attr):
    """
    This dynamically creates the module level variables, so if
    we don't call them, they are never created, saving time - mostly in the CLI.
    """
    if attr == "config":
        return get_config()
    elif attr == "leader_hostname":
        return get_leader_hostname()
    else:
        raise AttributeError


def reverse_config_section(section):
    """
    creates an inverted lookup from a config section. Useful to find LEDs and PWM.
    """
    return {v: k for k, v in section.items()}


@lru_cache(1)
def get_config():
    """
    This function intializes the configuration logic for the Pioreactor cluster.

    Locally, `config.ini` configurations can be overwritten by `unit_config.ini` (hence the very
    specific order we use in `config.read`)

    We also insert some **dynamic** config sections: PWM_reverse and leds_reverse. Ex: `PWM` is
    designed for users to edit:

        [PWM]
        0=stirring
        1=heating
        2=alt_media
        3=waste
        4=media


    and `PWM_reverse` is easier for computers to access (Note this is not in the config.ini file, but only in memory)

        [PWM_reverse]
        stirring=0
        heating=1
        alt_media=2
        waste=3
        media=4


    """
    config = configparser.ConfigParser()

    # https://stackoverflow.com/a/19359720/1895939
    config.optionxform = str

    config.BOOLEAN_STATES = {
        **{k: False for k in ["0", "false", "no", "off"]},
        **{k: True for k in ["1", "yes", "true", "on"]},
    }

    if "pytest" in sys.modules or os.environ.get("TESTING"):
        config.read("./config.dev.ini")
    else:
        global_config_path = "/home/pi/.pioreactor/config.ini"
        local_config_path = "/home/pi/.pioreactor/unit_config.ini"
        try:
            config.read([global_config_path, local_config_path])
        except configparser.MissingSectionHeaderError:
            # this can happen in the following situation:
            # on the leader (as worker) Rpi, the unit_config.ini is malformed. When leader_config.ini is fixed in the UI
            # pios sync tries to run, it uses a malformed unit_config.ini and hence the leader_config.ini can't be deployed
            # to replace the malformed unit_config.ini.
            from pioreactor.logging import create_logger

            logger = create_logger("config")
            logger.debug(
                "MissingSectionHeaderError raised. Check unit_config.ini on leader?"
            )
            config.read([global_config_path])

    # some helpful additions - see docs above
    config["leds_reverse"] = reverse_config_section(config["leds"])
    config["PWM_reverse"] = reverse_config_section(config["PWM"])

    return config


@lru_cache(1)
def get_leader_hostname():
    return get_config().get("network.topology", "leader_hostname")


def get_active_workers_in_inventory():
    # because we are not using config.getbool here, values like "0" are seen as true,
    # hence we use the built in config.BOOLEAN_STATES to determine truthiness
    config = get_config()
    return [
        unit
        for (unit, available) in config["network.inventory"].items()
        if config.BOOLEAN_STATES[available]
    ]
