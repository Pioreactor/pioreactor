# -*- coding: utf-8 -*-
import logging, uuid
from pioreactor.pubsub import create_client, publish
from pioreactor.whoami import (
    get_unit_name,
    am_I_active_worker,
    UNIVERSAL_EXPERIMENT,
    get_latest_experiment_name,
)
from pioreactor.config import config


class CustomMQTTtoUIFormatter(logging.Formatter):
    """Add in Error/Warning so the UI shows up in red/yellow."""

    FORMATS = {
        logging.ERROR: "[%(name)s] Error: %(message)s",
        logging.WARNING: "[%(name)s] Warning: %(message)s",
        "DEFAULT": "[%(name)s] %(message)s",
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMATS["DEFAULT"])
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class MQTTHandler(logging.Handler):
    """
    A handler class which writes logging records, appropriately formatted,
    to a MQTT server to a topic.
    """

    def __init__(self, topic, client, qos=2, retain=False, **mqtt_kwargs):
        logging.Handler.__init__(self)
        self.topic = topic
        self.qos = qos
        self.retain = retain
        self.mqtt_kwargs = mqtt_kwargs
        self.client = client

    def emit(self, record):
        msg = self.format(record)
        self.client.publish(
            self.topic, msg, qos=self.qos, retain=self.retain, **self.mqtt_kwargs
        )

        if config.getboolean("error_reporting", "send_to_Pioreactor_com", fallback=False):
            # turned off, by default
            if record.levelno == logging.ERROR:
                # TODO: build this service!
                publish(self.topic, msg, hostname="mqtt.pioreactor.com")


logging.raiseExceptions = False
# reduce logging from third party libs
logging.getLogger("sh").setLevel("ERROR")
logging.getLogger("paramiko").setLevel("ERROR")
logging.getLogger("sqlite3worker").setLevel("CRITICAL")


# file handler
file_handler = logging.FileHandler(config["logging"]["log_file"])
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)-2s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
)


# define a Handler which writes INFO messages or higher to the sys.stderr
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)-2s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
)


# create MQTT handlers for logging to DB
client = create_client(client_id=f"{get_unit_name()}-logging-{uuid.uuid1()}")

exp = get_latest_experiment_name() if am_I_active_worker() else UNIVERSAL_EXPERIMENT
topic = f"pioreactor/{get_unit_name()}/{exp}/logs/app"
mqtt_handler = MQTTHandler(topic, client)
mqtt_handler.setLevel(getattr(logging, config["logging"]["mqtt_log_level"]))
mqtt_handler.setFormatter(logging.Formatter("[%(name)s] %(levelname)-2s %(message)s"))

# create MQTT handlers for logging to UI
exp = get_latest_experiment_name() if am_I_active_worker() else UNIVERSAL_EXPERIMENT
topic = f"pioreactor/{get_unit_name()}/{exp}/app_logs_for_ui"
ui_handler = MQTTHandler(topic, client)
ui_handler.setLevel(getattr(logging, config["logging"]["ui_log_level"]))
ui_handler.setFormatter(CustomMQTTtoUIFormatter())


# add the handlers to the root logger
root_logger = logging.getLogger("")
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(console_handler)
root_logger.addHandler(mqtt_handler)
root_logger.addHandler(ui_handler)
root_logger.addHandler(file_handler)
