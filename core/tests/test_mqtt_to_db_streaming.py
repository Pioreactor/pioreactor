# -*- coding: utf-8 -*-
import sqlite3
from time import sleep

import pioreactor.background_jobs.leader.mqtt_to_db_streaming as m2db
from pioreactor import mureq
from pioreactor import structs
from pioreactor.automations import temperature  # noqa: F401
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.config import config
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_testing_experiment_name
from pioreactor.whoami import get_unit_name


def test_testing_data_is_filtered() -> None:
    unit = "unit"
    exp = get_testing_experiment_name()  # contains _testing_ prefix

    class TestJob(BackgroundJob):
        job_name = "test_job"
        published_settings = {
            "some_key": {
                "datatype": "json",
                "settable": False,
            },
        }

        def __init__(self, unit, experiment) -> None:
            super(TestJob, self).__init__(unit=unit, experiment=experiment)
            self.some_key = {"int": 4, "ts": 1}

    def parse_setting(topic, payload) -> dict:
        raise ValueError()  # never hit, since we exit early

    parsers = [
        m2db.TopicToParserToTable(
            "pioreactor/+/+/test_job/some_key",
            parse_setting,
            "table_setting",
        )
    ]

    with m2db.MqttToDBStreamer(unit, exp, parsers):
        with collect_all_logs_of_level("ERROR", unit, exp) as bucket:
            t = TestJob(unit=unit, experiment=exp)
            t.clean_up()
            sleep(1)

        assert len(bucket) == 0


def test_updated_heater_dc() -> None:
    unit = get_unit_name()
    exp = "test_updated_heater_dc"
    connection = sqlite3.connect(config["storage"]["database"])
    cursor = connection.cursor()

    cursor.executescript("DROP TABLE IF EXISTS temperature_automation_events;")
    cursor.executescript(
        mureq.get(
            "https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/sql/create_tables.sql"
        ).content.decode("utf-8")
    )

    connection.commit()

    parsers = [
        m2db.TopicToParserToTable(
            "pioreactor/+/+/temperature_automation/latest_event",
            m2db.parse_automation_event,
            "temperature_automation_events",
        ),
    ]

    with m2db.MqttToDBStreamer(unit, exp, parsers):
        sleep(1)
        publish(
            f"pioreactor/{unit}/test/temperature_automation/latest_event",
            '{"event_name":"UpdatedHeaterDC","message":"delta_dc=3.28125","data":{"current_dc":null,"delta_dc":3.28125}}',
        )
        sleep(5)

    cursor.execute("SELECT * FROM temperature_automation_events WHERE pioreactor_unit=?", (unit,))
    results = cursor.fetchall()
    assert len(results) == 1


def test_dosing_events_land_in_db() -> None:
    from pioreactor.actions.pump import add_media

    unit = get_unit_name()
    exp = "test_dosing_events_land_in_db"
    connection = sqlite3.connect(config["storage"]["database"])
    cursor = connection.cursor()

    cursor.executescript("DROP TABLE IF EXISTS dosing_events;")
    cursor.executescript("DROP TRIGGER IF EXISTS update_pioreactor_unit_activity_data_from_dosing_events;")
    cursor.executescript(
        mureq.get(
            "https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/sql/create_tables.sql"
        ).content.decode("utf-8")
    )
    cursor.executescript(
        mureq.get(
            "https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/sql/create_triggers.sql"
        ).content.decode("utf-8")
    )

    connection.commit()

    parsers = [
        m2db.TopicToParserToTable("pioreactor/+/+/dosing_events", m2db.parse_dosing_events, "dosing_events"),
    ]

    with m2db.MqttToDBStreamer(unit, exp, parsers) as job:

        sleep(1)
        add_media(
            unit,
            exp,
            ml=1,
            calibration=structs.SimplePeristalticPumpCalibration(
                calibration_name="test",
                curve_data_=structs.PolyFitCoefficients(coefficients=[1.0, 0.0]),
                recorded_data={"x": [], "y": []},
                dc=60,
                hz=100,
                created_at=current_utc_datetime(),
                voltage=-1.0,
                calibrated_on_pioreactor_unit=unit,
            ),
            source_of_event="test_suite",
            logger=job.logger,
            mqtt_client=job.pub_client,
        )
        sleep(1)

    cursor.execute("SELECT * FROM dosing_events WHERE pioreactor_unit=?", (unit,))
    results = cursor.fetchall()
    assert len(results) == 2


def test_empty_payload_is_filtered_early() -> None:
    unit = "unit"
    exp = "test_empty_payload_is_filtered_early"

    class TestJob(BackgroundJob):
        job_name = "test_job"
        published_settings = {
            "some_key": {
                "datatype": "json",
                "settable": False,
            },
        }

        def __init__(self, unit, experiment) -> None:
            super(TestJob, self).__init__(unit=unit, experiment=experiment)
            self.some_key = None

    def parse_setting(topic, payload) -> dict:
        raise ValueError()  # never hit, since we exit early

    # turn on our mqtt to db
    parsers = [
        m2db.TopicToParserToTable(
            "pioreactor/+/+/test_job/some_key",
            parse_setting,
            "table_setting",
        )
    ]

    with m2db.MqttToDBStreamer(unit, exp, parsers):
        with collect_all_logs_of_level("ERROR", unit, exp) as bucket:
            t = TestJob(unit=unit, experiment=exp)
            t.clean_up()
            sleep(1)

        assert len(bucket) == 0


def test_produce_metadata() -> None:
    v = m2db.produce_metadata("pioreactor/leader/exp1/this/is/a/test")
    assert v.pioreactor_unit == "leader"
    assert v.experiment == "exp1"
    assert v.rest_of_topic == ["this", "is", "a", "test"]


def test_table_does_not_exist_in_db_but_parser_exists() -> None:
    unit = "unit"
    exp = "test_table_does_not_exist_in_db_but_parser_exists"

    class TestJob(BackgroundJob):
        job_name = "test_job"
        published_settings = {
            "some_key": {
                "datatype": "string",
                "settable": False,
            },
        }

        def __init__(self, unit, experiment) -> None:
            super(TestJob, self).__init__(unit=unit, experiment=experiment)
            self.some_key = "where_am_i"

    def parse_setting(topic, payload) -> dict:
        return {"some_key": payload}

    # turn on our mqtt to db
    parsers = [
        m2db.TopicToParserToTable(
            "pioreactor/+/+/test_job/some_key",
            parse_setting,
            "table_setting",  # this table does not exist
        )
    ]

    with m2db.MqttToDBStreamer(unit, exp, parsers):
        with collect_all_logs_of_level("ERROR", unit, exp) as bucket:
            t = TestJob(unit=unit, experiment=exp)
            sleep(2)
            t.clean_up()

        assert len(bucket) == 0
