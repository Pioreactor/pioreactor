# -*- coding: utf-8 -*-
import logging
from pioreactor.pubsub import publish
from pioreactor.whoami import (
    get_unit_from_hostname,
    am_I_leader,
    UNIVERSAL_EXPERIMENT,
    get_latest_experiment_name,
)
from pioreactor.config import config


class MQTTHandler(logging.Handler):
    """
    A handler class which writes logging records, appropriately formatted,
    to a MQTT server to a topic.
    """

    def __init__(self, topic, qos=0, retain=False, **mqtt_kwargs):
        logging.Handler.__init__(self)
        self.topic = topic
        self.qos = qos
        self.retain = retain
        self.mqtt_kwargs = mqtt_kwargs

    def emit(self, record):
        msg = self.format(record)
        publish(self.topic, msg, qos=self.qos, retain=self.retain, **self.mqtt_kwargs)


class RejectShLogs(logging.Filter):
    """
    the module sh creates logs internally (so things get weird when we tail the log file using sh)
    this class filters the logs
    """

    def filter(self, record):
        return not record.name.startswith("sh.")


# ignore any issues with logging
logging.raiseExceptions = False
reject_sh_filter = RejectShLogs()

# file handler
file_handler = logging.FileHandler(config["logging"]["log_file"])
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)-2s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
)
file_handler.addFilter(reject_sh_filter)


# define a Handler which writes INFO messages or higher to the sys.stderr
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)-2s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
)
console_handler.addFilter(reject_sh_filter)


# create MQTT logger
exp = UNIVERSAL_EXPERIMENT if am_I_leader() else get_latest_experiment_name()
topic = f"pioreactor/{get_unit_from_hostname()}/{exp}/log"
mqtt_handler = MQTTHandler(topic)
mqtt_handler.setLevel(logging.INFO)
mqtt_handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
mqtt_handler.addFilter(reject_sh_filter)


# add the handlers to the root logger
root_logger = logging.getLogger("")
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(console_handler)
root_logger.addHandler(mqtt_handler)
root_logger.addHandler(file_handler)
