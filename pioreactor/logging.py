# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from logging import handlers
from time import sleep
from typing import TYPE_CHECKING

from json_log_formatter import JSONFormatter  # type: ignore

from pioreactor.config import config
from pioreactor.exc import NotAssignedAnExperimentError
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT

if TYPE_CHECKING:
    from pioreactor.pubsub import Client

logging.raiseExceptions = False

PIOREACTOR_LOG_FORMAT = logging.Formatter(
    "%(asctime)s [%(name)s] %(levelname)-2s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)


def add_logging_level(levelName: str, levelNum: int) -> None:
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

    def logForLevel(self: logging.Logger, message: str, *args, **kwargs) -> None:
        if self.isEnabledFor(levelNum):
            self._log(levelNum, message, args, **kwargs)

    def logToRoot(message: str, *args, **kwargs) -> None:
        logging.log(levelNum, message, *args, **kwargs)

    logging.addLevelName(levelNum, levelName)
    setattr(logging, levelName, levelNum)
    setattr(logging.Logger, methodName, logForLevel)
    setattr(logging.LoggerAdapter, methodName, logForLevel)
    setattr(logging, methodName, logToRoot)


NOTICE = logging.INFO + 5
add_logging_level("NOTICE", NOTICE)


class CustomLogger(logging.LoggerAdapter):
    def notice(self, msg, *args, **kwargs):
        self.log(NOTICE, msg, *args, **kwargs)

    def clean_up(self):
        handlers = self.logger.handlers[:]
        for handler in handlers:
            self.logger.removeHandler(handler)
            handler.close()


class CustomisedJSONFormatter(JSONFormatter):
    def json_record(self, message: str, extra: dict, record: logging.LogRecord) -> dict:
        from pioreactor.utils.timing import current_utc_timestamp

        extra["message"] = message
        extra["level"] = record.levelname
        extra["task"] = record.name
        extra["timestamp"] = current_utc_timestamp()
        extra["source"] = getattr(record, "source", None)  # type: ignore

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
        topic_prefix: str,
        client: Client,
        qos: int = 0,
        retain: bool = False,
        **mqtt_kwargs,
    ) -> None:
        logging.Handler.__init__(self)
        self.topic_prefix = topic_prefix
        self.qos = qos
        self.retain = retain
        self.mqtt_kwargs = mqtt_kwargs
        self.client = client

    def emit(self, record) -> None:
        payload = self.format(record)

        attempts = 0
        max_attempts = 10
        while not self.client.is_connected() and attempts < max_attempts:
            sleep(0.01)
            attempts += 1
            if attempts == max_attempts:
                return

        mqtt_msg = self.client.publish(
            f"{self.topic_prefix}/{record.levelname.lower()}",
            payload,
            qos=self.qos,
            retain=self.retain,
            **self.mqtt_kwargs,
        )
        # if Python exits too quickly, the last msg might never make it to the broker.
        mqtt_msg.wait_for_publish(timeout=2)

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        super().close()


def create_logger(
    name: str,
    unit: str | None = None,
    experiment: str | None = None,
    source: str = "app",
    to_mqtt: bool = True,
    pub_client: Client | None = None,
) -> CustomLogger:
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
    import colorlog
    from pioreactor.pubsub import create_client

    logger = logging.getLogger(name)

    if len(logger.handlers) > 0:
        return CustomLogger(logger, {"source": source})  # type: ignore

    logger.setLevel(logging.DEBUG)

    if unit is None:
        unit = get_unit_name()

    if experiment is None:
        # this fails if we aren't able to connect to leader, hence the to_mqtt check
        if to_mqtt:
            try:
                experiment = get_assigned_experiment_name(unit)
            except NotAssignedAnExperimentError:
                experiment = UNIVERSAL_EXPERIMENT
        else:
            experiment = UNIVERSAL_EXPERIMENT

    # file handler
    file_handler = handlers.WatchedFileHandler(config["logging"]["log_file"])
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(PIOREACTOR_LOG_FORMAT)
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
                "CRITICAL": "red",
            },
        )
    )

    # add local log handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    if to_mqtt:
        if pub_client is None:
            pub_client = create_client(
                client_id=f"{name}-logging-{unit}-{experiment}",
                max_connection_attempts=2,
                keepalive=15 * 60,
            )
        assert pub_client is not None

        # create MQTT handlers for logs table
        topic_prefix = (
            f"pioreactor/{unit}/{experiment}/logs/{source}"  # NOTE: we later append the log-level, ex: /debug
        )
        mqtt_to_db_handler = MQTTHandler(topic_prefix, pub_client)
        mqtt_to_db_handler.setLevel(logging.DEBUG)
        mqtt_to_db_handler.setFormatter(CustomisedJSONFormatter())

        # add MQTT/remote log handlers
        logger.addHandler(mqtt_to_db_handler)

    return CustomLogger(logger, {"source": source})  # type: ignore
