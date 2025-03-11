# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import os
from contextlib import contextmanager
from functools import cache
from pathlib import Path


def __getattr__(attr):  # type: ignore
    """
    This dynamically creates the module level variables, so if
    we don't call them, they are never created, saving time - mostly in the CLI.
    """
    if attr == "leader_hostname":
        return get_leader_hostname()
    elif attr == "leader_address":
        return get_leader_address()
    elif attr == "mqtt_address":
        return get_mqtt_address()
    else:
        raise AttributeError


class ConfigParserMod(configparser.ConfigParser):
    # https://stackoverflow.com/a/19359720/1895939
    optionxform = str  # type: ignore
    BOOLEAN_STATES = {
        **{k: False for k in ("0", "false", "no", "off")},
        **{k: True for k in ("1", "yes", "true", "on")},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, allow_no_value=True, **kwargs)

    def invert_section(self, section: str) -> dict[str, str]:
        """
        creates an inverted lookup from a config section. Useful to find LEDs and PWM.
        """
        section_without_empties = {k: v for k, v in self[section].items() if v != ""}
        reversed_section = {v: k for k, v in section_without_empties.items()}
        return reversed_section

    def _get_conv(self, section, option, conv, *, raw=False, vars=None, fallback=None, **kwargs):
        try:
            return self._get(section, conv, option, raw=raw, vars=vars, fallback=fallback, **kwargs)
        except TypeError as e:
            from pioreactor.logging import create_logger

            create_logger("read config").error(f"Error in [{section}] parameter {option}: {e}")
            raise e

    def getboolean(self, section: str, option: str, *args, **kwargs) -> bool:
        try:
            return super().getboolean(section, option, *args, **kwargs)
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            if "fallback" in kwargs:
                return kwargs["fallback"]

            from pioreactor.logging import create_logger

            logger = create_logger("read config")

            msg = f"""Not found in configuration: '{section}.{option}'. Are you missing the following in your config?

[{section}]
{option}=some value

"""

            logger.warning(msg)
            raise e

    def get(self, section: str, option: str, *args, **kwargs) -> str:  # type: ignore[override]
        try:
            return super().get(section, option, *args, **kwargs)
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            if "fallback" in kwargs:
                return kwargs["fallback"]

            from pioreactor.logging import create_logger

            create_logger("read config").warning(
                f"""Not found in configuration: '{section}.{option}'. Are you missing the following in your config?

[{section}]
{option}=some value

"""
            )
            raise e


@cache
def get_config() -> ConfigParserMod:
    """
    This function reads from disk and initializes the configuration logic for the Pioreactor cluster.

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

    and `od_config.photodiode_channel_reverse`

    """
    config = ConfigParserMod(strict=False)
    from pioreactor.whoami import is_testing_env

    if is_testing_env():
        global_config_path = os.environ.get("GLOBAL_CONFIG", "./config.dev.ini")
        local_config_path = os.environ.get("LOCAL_CONFIG", "")
    else:
        global_config_path = "/home/pioreactor/.pioreactor/config.ini"
        local_config_path = "/home/pioreactor/.pioreactor/unit_config.ini"

    if not Path(global_config_path).exists():
        raise FileNotFoundError(
            f"Configuration file at {global_config_path} is missing. Has it completed initializing? Does it need to connect to a leader? Alternatively, use the env variable GLOBAL_CONFIG to specify its location."
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
        pass

    # some helpful additions - see docs above
    if "leds" in config:
        config["leds_reverse"] = config.invert_section("leds")
    if "PWM" in config:
        config["PWM_reverse"] = config.invert_section("PWM")
    if "od_config.photodiode_channel" in config:
        config["od_config.photodiode_channel_reverse"] = config.invert_section("od_config.photodiode_channel")

    # add this for hostname resolution using config.ini, see pioreactor.utils.networking.resolve_to_address
    if "cluster.addresses" not in config:
        config.add_section("cluster.addresses")

    leader_hostname = config.get("cluster.topology", "leader_hostname")
    leader_address = config.get("cluster.topology", "leader_address")
    config.set("cluster.addresses", leader_hostname, leader_address)

    return config


config = get_config()


@cache
def get_leader_hostname() -> str:
    return get_config().get("cluster.topology", "leader_hostname", fallback="localhost")


@cache
def get_leader_address() -> str:
    return get_config().get("cluster.topology", "leader_address", fallback="localhost")


@cache
def get_mqtt_address() -> str:
    return get_config().get("mqtt", "broker_address", fallback=get_leader_address())


# @contextmanager
def temporary_config_change(config: ConfigParserMod, section: str, parameter: str, new_value: str):
    """
    A context manager to temporarily change a value in a ConfigParser object.
    """
    return temporary_config_changes(config, [(section, parameter, new_value)])


@contextmanager
def temporary_config_changes(config, changes: list[tuple[str, str, str | None]]):
    """
    A context manager to temporarily change multiple values in a ConfigParser object.

    Parameters:
      config: The ConfigParser object.
      changes: An iterable of tuples, each containing (section, parameter, new_value).
    """
    # Dictionary to store the original values for restoration.
    originals = {}
    to_delete = []

    try:
        for section, parameter, new_value in changes:
            if config.has_section(section) and config.has_option(section, parameter):
                # Save the original value
                originals[(section, parameter)] = config.get(section, parameter)
                # Apply the temporary change
                config.set(section, parameter, new_value)
            else:
                # delete after
                config.set(section, parameter, new_value)
                to_delete.append((section, parameter))
        yield
    finally:
        # Restore all the original values
        for (section, parameter), original_value in originals.items():
            config.set(section, parameter, original_value)
        for section, parameter in to_delete:
            config.remove_option(section, parameter)
