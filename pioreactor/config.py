# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import os
from functools import lru_cache

from pioreactor.whoami import is_testing_env


def __getattr__(attr):  # type: ignore
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


class ConfigParserMod(configparser.ConfigParser):

    # https://stackoverflow.com/a/19359720/1895939
    optionxform = str  # type: ignore
    BOOLEAN_STATES = {
        **{k: False for k in ["0", "false", "no", "off"]},
        **{k: True for k in ["1", "yes", "true", "on"]},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, allow_no_value=True, **kwargs)

    def invert_section(self, section: str) -> dict[str, str]:
        """
        creates an inverted lookup from a config section. Useful to find LEDs and PWM.
        """
        section_without_empties = {k: v for k, v in self[section].items() if v != ""}
        reversed_section = {v: k for k, v in section_without_empties.items()}

        if len(reversed_section) != len(section_without_empties):

            values = list(self[section].values())
            dups = set([x for x in values if values.count(x) > 1])

            # can't use logger, as the logger module uses config.py...
            # TODO: I could use paho to publish to log topic in localhost mosquitto?
            print(
                f"WARNING Duplicate values, `{next(iter(dups))}`, found in section `{section}`. This may lead to unexpected behavior. Please give unique names."
            )

        return reversed_section

    def get(self, section: str, option: str, *args, **kwargs):  # type: ignore
        try:
            return super().get(section, option, *args, **kwargs)
        except (configparser.NoSectionError, configparser.NoOptionError):
            from pioreactor.logging import create_logger

            create_logger("read config").error(
                f"""No found in configuration: '{section}.{option}'. Are you missing the following in your config?

[{section}]
{option}=some value

"""
            )
            raise


@lru_cache(1)
def get_config():
    """
    This function initializes the configuration logic for the Pioreactor cluster.

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
    config = ConfigParserMod()

    if is_testing_env():
        global_config_path = "./config.dev.ini"
        local_config_path = ""
    else:
        global_config_path = "/home/pioreactor/.pioreactor/config.ini"
        local_config_path = "/home/pioreactor/.pioreactor/unit_config.ini"
        if not os.path.isfile(global_config_path):
            raise FileNotFoundError(
                "/home/pioreactor/.pioreactor/config.ini is missing from this Pioreactor. Has it completed initializing? Does it need to connect to a leader?"
            )

    config_files = [global_config_path, local_config_path]

    try:
        config.read(config_files)
    except configparser.MissingSectionHeaderError as e:
        # this can happen in the following situation:
        # on the leader (as worker) Rpi, the unit_config.ini is malformed. When leader_config.ini is fixed in the UI
        # pios sync tries to run, it uses a malformed unit_config.ini and hence the leader_config.ini can't be deployed
        # to replace the malformed unit_config.ini.
        print(
            "Bad config state. Check /home/pioreactor/.pioreactor/unit_config.ini on leader for malformed configuration?"
        )
        raise e
    except configparser.DuplicateSectionError as e:
        print(e)
        raise e

    # some helpful additions - see docs above
    if "leds" in config:
        config["leds_reverse"] = config.invert_section("leds")
    if "PWM" in config:
        config["PWM_reverse"] = config.invert_section("PWM")

    return config


@lru_cache(1)
def get_leader_hostname() -> str:
    return get_config().get("network.topology", "leader_hostname", fallback="localhost")


def get_active_workers_in_inventory() -> tuple[str, ...]:
    # because we are not using config.getboolean here, values like "0" are seen as true,
    # hence we use the built in config.BOOLEAN_STATES to determine truthiness
    config = get_config()
    return tuple(
        str(unit)
        for (unit, available) in config["network.inventory"].items()
        if config.BOOLEAN_STATES[available]
    )
