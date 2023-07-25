# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from logging import handlers
from logging import Logger
from typing import Optional

import colorlog
from json_log_formatter import JSONFormatter  # type: ignore

from pioreactor.config import config
from pioreactor.pubsub import Client
from pioreactor.pubsub import create_client
from pioreactor.pubsub import publish_to_pioreactor_cloud
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import am_I_active_worker
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


logging.raiseExceptions = False


def add_logging_level(levelName, levelNum):
    """
    Comprehensively adds a new logging level to the `logging` module and the
    currently configured logging class.

    `levelName` becomes an attribute of the `logging` module with the value
    `levelNum`. `methodName` becomes a convenience method for both `logging`
    itself and the Logger class.

    Example
    -------
    >>> addLoggingLevel('TRACE', logging.DEBUG - 5)
    >>> logging.getLogger(__name__).setLevel("TRACE")
    >>> logging.getLogger(__name__).trace('that worked')
    >>> logging.trace('so did this')
    >>> logging.TRACE
    5

    """
    methodName = levelName.lower()

    def logForLevel(self, message, *args, **kwargs):
        if self.isEnabledFor(levelNum):
            self._log(levelNum, message, args, **kwargs)

    def logToRoot(message, *args, **kwargs):
        logging.log(levelNum, message, *args, **kwargs)

    logging.addLevelName(levelNum, levelName)
    setattr(logging, levelName, levelNum)
    setattr(logging.Logger, methodName, logForLevel)
    setattr(logging.LoggerAdapter, methodName, logForLevel)
    setattr(logging, methodName, logToRoot)


NOTICE = logging.INFO + 5
add_logging_level("NOTICE", NOTICE)


class CustomLoggerAdapter(logging.LoggerAdapter):
    def notice(self, msg, *args, **kwargs):
        self.log(NOTICE, msg, *args, **kwargs)


class CustomisedJSONFormatter(JSONFormatter):
    def json_record(self, message: str, extra: dict, record: logging.LogRecord) -> dict:
        extra["message"] = message
        extra["level"] = record.levelname
        extra["task"] = record.name
        extra["timestamp"] = current_utc_timestamp()
        extra["source"] = record.source  # type: ignore

        if record.exc_info:
            extra["message"] += "\n" + self.formatException(record.exc_info)

        return extra


class MQTTHandler(logging.Handler):
    """
    A handler class which writes logging records, appropriately formatted,
    to a MQTT server to a topic.
    """

    def __init__(
        self,
        topic: str,
        client: Client,
        qos: int = 0,
        retain: bool = False,
        **mqtt_kwargs,
    ) -> None:
        logging.Handler.__init__(self)
        self.topic = topic
        self.qos = qos
        self.retain = retain
        self.mqtt_kwargs = mqtt_kwargs
        self.client = client

    def emit(self, record) -> None:
        payload = self.format(record)

        if not self.client.is_connected():
            return

        mqtt_msg = self.client.publish(
            self.topic, payload, qos=self.qos, retain=self.retain, **self.mqtt_kwargs
        )

        if (record.levelno == logging.ERROR) and config.getboolean(
            "data_sharing_with_pioreactor", "send_errors_to_Pioreactor", fallback=False
        ):
            publish_to_pioreactor_cloud("reported_errors", data_str=payload)

        # if Python exits too quickly, the last msg might never make it to the broker.
        mqtt_msg.wait_for_publish(timeout=2)

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        super().close()


def create_logger(
    name: str,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    source: str = "app",
    to_mqtt: bool = True,
    mqtt_hostname: Optional[str] = None,
) -> Logger:
    """

    Parameters
    -----------
    name: string
        the name of the logger
    source:
        "app" for the core Pioreactor codebase, else the name of the plugin.
    to_mqtt: bool
        connect and log to MQTT
    """

    logger = logging.getLogger(name)

    if len(logger.handlers) > 0:
        return CustomLoggerAdapter(logger, {"source": source})  # type: ignore

    logger.setLevel(logging.DEBUG)

    if unit is None:
        unit = get_unit_name()

    if experiment is None:
        # this fails if we aren't able to connect to leader, hence the to_mqtt check
        if to_mqtt:
            experiment = get_latest_experiment_name()
        else:
            experiment = UNIVERSAL_EXPERIMENT

    # file handler
    file_handler = handlers.WatchedFileHandler(config["logging"]["log_file"])
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)-2s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    # define a Handler which writes to the sys.stderr
    console_handler = logging.StreamHandler()
    console_handler.setLevel(config.get("logging", "console_log_level", fallback="DEBUG"))
    console_handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s %(levelname)-6s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "NOTICE": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
        )
    )

    # add local log handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    if to_mqtt:
        pub_client = create_client(
            hostname=mqtt_hostname,
            client_id=f"{name}-logging-{unit}-{experiment}",
            max_connection_attempts=2,
            keepalive=15 * 60,
        )

        experiment = experiment if am_I_active_worker() else UNIVERSAL_EXPERIMENT

        # create MQTT handlers for logs table
        topic = f"pioreactor/{unit}/{experiment}/logs/{source}"
        mqtt_to_db_handler = MQTTHandler(topic, pub_client)
        mqtt_to_db_handler.setLevel(logging.DEBUG)
        mqtt_to_db_handler.setFormatter(CustomisedJSONFormatter())

        # add MQTT/remote log handlers
        logger.addHandler(mqtt_to_db_handler)

    return CustomLoggerAdapter(logger, {"source": source})  # type: ignore
