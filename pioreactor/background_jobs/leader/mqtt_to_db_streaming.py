# -*- coding: utf-8 -*-
"""
This job runs on the leader
"""
from __future__ import annotations

from dataclasses import dataclass
from json import dumps
from json import loads
from typing import Callable
from typing import Optional

import click

from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.config import config
from pioreactor.pubsub import QOS
from pioreactor.types import MQTTMessage
from pioreactor.types import MQTTMessagePayload
from pioreactor.utils.timing import current_utc_time
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


@dataclass
class MetaData:
    pioreactor_unit: str
    experiment: str


@dataclass
class TopicToParserToTable:
    topic: str
    parser: Callable[[str, MQTTMessagePayload], Optional[dict]]
    table: str


class MqttToDBStreamer(BackgroundJob):

    topics_to_tables_from_plugins: list[TopicToParserToTable] = []

    def __init__(
        self, topics_to_tables: list[TopicToParserToTable], unit: str, experiment: str
    ) -> None:

        from sqlite3worker import Sqlite3Worker

        super().__init__(
            job_name="mqtt_to_db_streaming", experiment=experiment, unit=unit
        )
        self.sqliteworker = Sqlite3Worker(
            config["storage"]["database"], max_queue_size=250, raise_on_error=False
        )

        topics_to_tables.extend(self.topics_to_tables_from_plugins)

        topics_and_callbacks = [
            {
                "topic": topic_to_table.topic,
                "callback": self.create_on_message_callback(
                    topic_to_table.parser, topic_to_table.table
                ),
            }
            for topic_to_table in topics_to_tables
        ]

        self.initialize_callbacks(topics_and_callbacks)

    def on_disconnected(self) -> None:
        self.sqliteworker.close()  # close the db safely

    def create_on_message_callback(
        self, parser: Callable[[str, MQTTMessagePayload], Optional[dict]], table: str
    ) -> Callable:
        def _callback(message: MQTTMessage) -> None:
            # TODO: filter testing experiments here?
            try:
                new_row = parser(message.topic, message.payload)
            except Exception as e:
                self.logger.error(e)
                self.logger.debug(
                    f"Error in {parser.__name__}. message.payload that caused error: `{message.payload.decode()}`"
                )
                return

            if new_row is None:
                # parsers can return None to exit out.
                return

            cols_placeholder = ", ".join(new_row.keys())
            values_placeholder = ", ".join([":" + c for c in new_row.keys()])
            SQL = f"""INSERT INTO {table} ({cols_placeholder}) VALUES ({values_placeholder})"""
            try:
                self.sqliteworker.execute(SQL, new_row)  # type: ignore
            except Exception as e:
                self.logger.error(e)
                self.logger.debug(f"SQL that caused error: `{SQL}`")
                return

        return _callback

    def initialize_callbacks(self, topics_and_callbacks: list[dict]) -> None:
        for topic_and_callback in topics_and_callbacks:
            self.subscribe_and_callback(
                topic_and_callback["callback"],
                topic_and_callback["topic"],
                qos=QOS.EXACTLY_ONCE,
                allow_retained=False,
            )


def produce_metadata(topic: str) -> tuple[MetaData, list[str]]:
    # helper function for parsers below
    split_topic = topic.split("/")
    return (
        MetaData(split_topic[1], split_topic[2]),
        split_topic,
    )


def start_mqtt_to_db_streaming() -> MqttToDBStreamer:

    ###################
    # parsers
    ###################
    # - must return a dictionary with the column names (order isn't important)
    # - `produce_metadata` is a helper function, see definition.
    # - parsers can return None as well, to skip adding the message to the database.
    #

    def parse_od(topic: str, payload) -> dict:
        metadata, split_topic = produce_metadata(topic)
        payload_dict = loads(payload)

        try:
            angle = int(payload_dict["angle"])
        except TypeError:
            angle = -1

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "od_reading_v": payload_dict["voltage"],
            "angle": angle,
            "channel": split_topic[-1],
        }

    def parse_od_filtered(topic: str, payload: MQTTMessagePayload) -> dict:
        metadata, split_topic = produce_metadata(topic)
        payload_dict = loads(payload)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "normalized_od_reading": payload_dict["od_filtered"],
        }

    def parse_od_blank(
        topic: str, payload: Optional[MQTTMessagePayload]
    ) -> Optional[dict]:
        metadata, split_topic = produce_metadata(topic)
        if not payload:
            return None
        payload_dict = loads(payload)
        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "od_reading_v": payload_dict["od_reading_v"],
            "channel": split_topic[-1],
        }

    def parse_dosing_events(topic: str, payload: MQTTMessagePayload) -> dict:
        payload_dict = loads(payload)
        metadata, _ = produce_metadata(topic)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "volume_change_ml": payload_dict["volume_change"],
            "event": payload_dict["event"],
            "source_of_event": payload_dict["source_of_event"],
        }

    def parse_led_events(topic: str, payload: MQTTMessagePayload) -> dict:
        payload_dict = loads(payload)
        metadata, _ = produce_metadata(topic)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "channel": payload_dict["channel"],
            "intensity": payload_dict["intensity"],
            "source_of_event": payload_dict["source_of_event"],
        }

    def parse_growth_rate(topic: str, payload: MQTTMessagePayload) -> dict:
        metadata, _ = produce_metadata(topic)
        payload_dict = loads(payload)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "rate": float(payload_dict["growth_rate"]),
        }

    def parse_temperature(
        topic: str, payload: Optional[MQTTMessagePayload]
    ) -> Optional[dict]:
        metadata, _ = produce_metadata(topic)

        if not payload:
            return None

        payload_dict = loads(payload)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "temperature_c": float(payload_dict["temperature"]),
        }

    def parse_alt_media_fraction(topic: str, payload: MQTTMessagePayload) -> dict:
        metadata, _ = produce_metadata(topic)
        payload = loads(payload)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": current_utc_time(),
            "alt_media_fraction": float(payload),
        }

    def parse_logs(topic: str, payload: MQTTMessagePayload) -> dict:
        metadata, split_topic = produce_metadata(topic)
        payload_dict = loads(payload)
        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "message": payload_dict["message"],
            "task": payload_dict["task"],
            "level": payload_dict["level"],
            "source": split_topic[-1],  # should be app, ui, etc.
        }

    def parse_kalman_filter_outputs(topic: str, payload: MQTTMessagePayload) -> dict:
        metadata, _ = produce_metadata(topic)
        payload_dict = loads(payload)
        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "state": dumps(payload_dict["state"]),
            "covariance_matrix": dumps(payload_dict["covariance_matrix"]),
        }

    def parse_automation_settings(topic: str, payload: MQTTMessagePayload) -> dict:
        payload_dict = loads(payload)
        return payload_dict

    def parse_stirring_rates(
        topic: str, payload: Optional[MQTTMessagePayload]
    ) -> Optional[dict]:
        if not payload:
            return None

        metadata, _ = produce_metadata(topic)
        payload_dict = loads(payload)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "measured_rpm": payload_dict["rpm"],
        }

    topics_to_tables = [
        TopicToParserToTable(
            "pioreactor/+/+/growth_rate_calculating/od_filtered",
            parse_od_filtered,
            "od_readings_filtered",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/od_reading/od_raw/+", parse_od, "od_readings_raw"
        ),
        TopicToParserToTable(
            "pioreactor/+/+/dosing_events", parse_dosing_events, "dosing_events"
        ),
        TopicToParserToTable("pioreactor/+/+/led_events", parse_led_events, "led_events"),
        TopicToParserToTable(
            "pioreactor/+/+/growth_rate_calculating/growth_rate",
            parse_growth_rate,
            "growth_rates",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/temperature_control/temperature",
            parse_temperature,
            "temperature_readings",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/dosing_automation/alt_media_fraction",
            parse_alt_media_fraction,
            "alt_media_fraction",
        ),
        TopicToParserToTable("pioreactor/+/+/logs/+", parse_logs, "logs"),
        TopicToParserToTable(
            "pioreactor/+/+/dosing_automation/dosing_automation_settings",
            parse_automation_settings,
            "dosing_automation_settings",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/led_automation/led_automation_settings",
            parse_automation_settings,
            "led_automation_settings",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/temperature_automation/temperature_automation_settings",
            parse_automation_settings,
            "temperature_automation_settings",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/growth_rate_calculating/kalman_filter_outputs",
            parse_kalman_filter_outputs,
            "kalman_filter_outputs",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/stirring/measured_rpm", parse_stirring_rates, "stirring_rates"
        ),
        TopicToParserToTable("pioreactor/+/+/od_blank/mean", parse_od_blank, "od_blanks"),
    ]

    return MqttToDBStreamer(
        topics_to_tables, experiment=UNIVERSAL_EXPERIMENT, unit=get_unit_name()
    )


@click.command(name="mqtt_to_db_streaming")
def click_mqtt_to_db_streaming():
    """
    (leader only) Send MQTT streams to the database. Parsers should return a dict of all the entries in the corresponding table.
    """
    import os

    os.nice(1)

    job = start_mqtt_to_db_streaming()
    job.block_until_disconnected()
