# -*- coding: utf-8 -*-
from __future__ import annotations

from json import dumps
from json import loads
from typing import Callable
from typing import Optional

import click
from msgspec import Struct
from msgspec.json import decode as msgspec_loads

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.config import config
from pioreactor.pubsub import QOS
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


class MetaData(Struct):
    pioreactor_unit: str
    experiment: str


class TopicToParserToTable(Struct):
    topic: str | list[str]
    parser: Callable[[str, pt.MQTTMessagePayload], Optional[dict]]
    table: str


class MqttToDBStreamer(BackgroundJob):

    topics_to_tables_from_plugins: list[TopicToParserToTable] = []

    def __init__(
        self, topics_to_tables: list[TopicToParserToTable], unit: str, experiment: str
    ) -> None:

        from sqlite3worker import Sqlite3Worker

        super().__init__(job_name="mqtt_to_db_streaming", experiment=experiment, unit=unit)
        self.sqliteworker = Sqlite3Worker(
            config["storage"]["database"], max_queue_size=250, raise_on_error=False
        )

        topics_to_tables.extend(self.topics_to_tables_from_plugins)

        topics_and_callbacks = [
            {
                "topic": topic_to_table.topic,
                "callback": self.create_on_message_callback(
                    topic_to_table.parser, topic_to_table.table  # type: ignore
                ),
            }
            for topic_to_table in topics_to_tables
        ]

        self.initialize_callbacks(topics_and_callbacks)

    def on_disconnected(self) -> None:
        self.sqliteworker.close()  # close the db safely

    def create_on_message_callback(
        self, parser: Callable[[str, pt.MQTTMessagePayload], Optional[dict]], table: str
    ) -> Callable:
        def _callback(message: pt.MQTTMessage) -> None:
            # TODO: filter testing experiments here?

            if not message.payload:
                # filter out empty payloads
                return

            try:
                new_row = parser(message.topic, message.payload)
            except Exception as e:
                self.logger.error(e)
                self.logger.debug(
                    f"Error in {parser.__name__}. message.payload that caused error: `{message.payload.decode()}`",
                    exc_info=True,
                )
                return

            if new_row is None:
                # parsers can return None to exit out.
                return

            cols_placeholder = ", ".join(new_row.keys())
            values_placeholder = ", ".join(":" + c for c in new_row.keys())
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


def produce_metadata(topic: str) -> MetaData:
    # helper function for parsers below
    split_topic = topic.split("/")
    return MetaData(split_topic[1], split_topic[2])


def start_mqtt_to_db_streaming() -> MqttToDBStreamer:

    ###################
    # parsers
    ###################
    # - must return a dictionary with the column names (order isn't important)
    # - `produce_metadata` is a helper function, see definition.
    # - parsers can return None as well, to skip adding the message to the database.
    #

    def parse_od(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)
        od_reading = msgspec_loads(payload, type=structs.ODReading)

        try:
            angle = int(od_reading.angle)
        except TypeError:
            angle = -1

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": od_reading.timestamp,
            "od_reading_v": od_reading.voltage,
            "angle": angle,
            "channel": od_reading.channel,
        }

    def parse_od_filtered(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)
        od_reading = msgspec_loads(payload, type=structs.ODFiltered)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": od_reading.timestamp,
            "normalized_od_reading": od_reading.od_filtered,
        }

    def parse_od_blank(topic: str, payload: pt.MQTTMessagePayload) -> Optional[dict]:
        metadata = produce_metadata(topic)
        od_reading = msgspec_loads(payload, type=structs.ODReading)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": od_reading.timestamp,
            "od_reading_v": od_reading.voltage,
            "channel": od_reading.channel,
            "angle": od_reading.angle,
        }

    def parse_ir_led_intensity(topic: str, payload: pt.MQTTMessagePayload) -> dict:

        metadata = produce_metadata(topic)

        payload_dict = loads(payload)
        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "relative_intensity": payload_dict["relative_intensity_of_ir_led"],
        }

    def parse_dosing_events(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        dosing_event = msgspec_loads(payload, type=structs.DosingEvent)
        metadata = produce_metadata(topic)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": dosing_event.timestamp,
            "volume_change_ml": dosing_event.volume_change,
            "event": dosing_event.event,
            "source_of_event": dosing_event.source_of_event,
        }

    def parse_led_change_events(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        led_event = msgspec_loads(payload, type=structs.LEDChangeEvent)
        metadata = produce_metadata(topic)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": led_event.timestamp,
            "channel": led_event.channel,
            "intensity": led_event.intensity,
            "source_of_event": led_event.source_of_event,
        }

    def parse_growth_rate(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)
        gr = msgspec_loads(payload, type=structs.GrowthRate)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": gr.timestamp,
            "rate": gr.growth_rate,
        }

    def parse_temperature(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)

        temp = msgspec_loads(payload, type=structs.Temperature)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": temp.timestamp,
            "temperature_c": temp.temperature,
        }

    def parse_automation_event(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)
        event = loads(
            payload
        )  # structs.AutomationEvent, but see https://github.com/jcrist/msgspec/issues/115#issuecomment-1146097674

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": current_utc_timestamp(),
            "message": event["message"],
            "data": dumps(event["data"]),
            "event_name": event["event_name"],
        }

    def parse_alt_media_fraction(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)
        payload = loads(payload)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": current_utc_timestamp(),
            "alt_media_fraction": float(payload),
        }

    def parse_logs(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)
        log = msgspec_loads(payload, type=structs.Log)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": log.timestamp,
            "message": log.message,
            "task": log.task,
            "level": log.level,
            "source": log.source,  # should be app, ui, etc.
        }

    def parse_kalman_filter_outputs(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)
        payload_dict = loads(payload)
        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": payload_dict["timestamp"],
            "state_0": payload_dict["state"][0],
            "state_1": payload_dict["state"][1],
            "state_2": payload_dict["state"][2],
            "cov_00": payload_dict["covariance_matrix"][0][0],
            "cov_01": payload_dict["covariance_matrix"][0][1],
            "cov_02": payload_dict["covariance_matrix"][0][2],
            "cov_11": payload_dict["covariance_matrix"][1][1],
            "cov_12": payload_dict["covariance_matrix"][1][2],
            "cov_22": payload_dict["covariance_matrix"][2][2],
        }

    def parse_automation_settings(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        payload_dict = loads(payload)
        return payload_dict

    def parse_stirring_rates(topic: str, payload: pt.MQTTMessagePayload) -> dict:
        metadata = produce_metadata(topic)
        rpms = msgspec_loads(payload, type=structs.MeasuredRPM)

        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": rpms.timestamp,
            "measured_rpm": rpms.measured_rpm,
        }

    topics_to_tables = [
        TopicToParserToTable(
            "pioreactor/+/+/growth_rate_calculating/od_filtered",
            parse_od_filtered,
            "od_readings_filtered",
        ),
        TopicToParserToTable("pioreactor/+/+/od_reading/od_raw/+", parse_od, "od_readings_raw"),
        TopicToParserToTable("pioreactor/+/+/dosing_events", parse_dosing_events, "dosing_events"),
        TopicToParserToTable(
            "pioreactor/+/+/led_change_events",
            parse_led_change_events,
            "led_change_events",
        ),
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
            "alt_media_fractions",
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
        TopicToParserToTable("pioreactor/+/+/od_blank/mean/+", parse_od_blank, "od_blanks"),
        TopicToParserToTable(
            "pioreactor/+/+/od_reading/relative_intensity_of_ir_led",
            parse_ir_led_intensity,
            "ir_led_intensities",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/dosing_automation/latest_event",
            parse_automation_event,
            "dosing_automation_events",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/led_automation/latest_event",
            parse_automation_event,
            "led_automation_events",
        ),
        TopicToParserToTable(
            "pioreactor/+/+/temperature_automation/latest_event",
            parse_automation_event,
            "temperature_automation_events",
        ),
    ]

    return MqttToDBStreamer(topics_to_tables, experiment=UNIVERSAL_EXPERIMENT, unit=get_unit_name())


@click.command(name="mqtt_to_db_streaming")
def click_mqtt_to_db_streaming():
    """
    (leader only) Send MQTT streams to the database. Parsers should return a dict of all the entries in the corresponding table.
    """
    import os

    os.nice(1)

    job = start_mqtt_to_db_streaming()
    job.block_until_disconnected()
