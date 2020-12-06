# -*- coding: utf-8 -*-
import logging
from pioreactor.pubsub import publish
from pioreactor.whoami import (
    get_unit_from_hostname,
    am_I_leader,
    UNIVERSAL_EXPERIMENT,
    get_latest_experiment_name,
)


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


logging.raiseExceptions = False
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)-2s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
    filename="./pioreactor.log",
    filemode="a",
)

# define a Handler which writes INFO messages or higher to the sys.stderr
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)-2s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
)

# create MQTT logger
exp = UNIVERSAL_EXPERIMENT if am_I_leader() else get_latest_experiment_name()
topic = f"pioreactor/{get_unit_from_hostname()}/{exp}/log"
mqtt_handler = MQTTHandler(topic)
mqtt_handler.setLevel(logging.INFO)
mqtt_handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))


# add the handler to the root logger
root_logger = logging.getLogger("")
root_logger.addHandler(console_handler)
root_logger.addHandler(mqtt_handler)
