# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
from time import sleep

import pioreactor.background_jobs.leader.mqtt_to_db_streaming as m2db
import pytest
from pioreactor import mureq
from pioreactor import structs
from pioreactor.automations import temperature  # noqa: F401
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.config import config
from pioreactor.config import temporary_config_changes
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.utils import local_persistent_storage
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


@pytest.mark.xfail()
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
                curve_data_=[1.0, 0.0],
                curve_type="poly",
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


@pytest.mark.xfail(reason="we stopped adding to kalman filter table in 25.1.x release")
def test_kalman_filter_entries() -> None:
    with temporary_config_changes(
        config,
        [
            ("storage", "database", "test.sqlite"),
            ("od_reading.config", "samples_per_second", "0.2"),
            ("od_config.photodiode_channel", "1", "135"),
            ("od_config.photodiode_channel", "2", "90"),
        ],
    ):
        unit = "unit"
        exp = "test_kalman_filter_entries"

        # init the database
        connection = sqlite3.connect(config["storage"]["database"])
        cursor = connection.cursor()

        cursor.executescript("DROP TABLE IF EXISTS kalman_filter_outputs;")
        cursor.executescript(
            mureq.get(
                "https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/sql/create_tables.sql"
            ).content.decode("utf-8")
        )
        connection.commit()

        with local_persistent_storage("od_normalization_mean") as cache:
            cache[exp] = json.dumps({"1": 0.5, "2": 0.5})

        with local_persistent_storage("od_normalization_variance") as cache:
            cache[exp] = json.dumps({"1": 1e-6, "2": 1e-4})

        # turn on our mqtt to db
        parsers = [
            m2db.TopicToParserToTable(
                "pioreactor/+/+/growth_rate_calculating/kalman_filter_outputs",
                m2db.parse_kalman_filter_outputs,
                "kalman_filter_outputs",
            )
        ]

        # turn on data collection
        interval = 0.5

        with (
            start_od_reading(
                {"1": "135", "2": "90"},
                interval=interval,
                fake_data=True,
                unit=unit,
                experiment=exp,
            ),
            GrowthRateCalculator(unit=unit, experiment=exp),
            m2db.MqttToDBStreamer(unit, exp, parsers),
        ):
            # let data collect
            sleep(10)

            cursor.execute("SELECT * FROM kalman_filter_outputs WHERE experiment = ?", (exp,))
            results = cursor.fetchall()
            assert len(results) > 0

            cursor.execute(
                "SELECT state_0, state_1, state_2 FROM kalman_filter_outputs WHERE experiment = ? ORDER BY timestamp DESC LIMIT 1",
                (exp,),
            )
            results = cursor.fetchone()
            assert results[0] != 0.0
            assert results[1] != 0.0
            assert results[2] != 0.0

        cursor.execute(
            "SELECT cov_00, cov_11, cov_22 FROM kalman_filter_outputs WHERE experiment = ? ORDER BY timestamp DESC LIMIT 1",
            (exp,),
        )
        results = cursor.fetchone()

        assert results[0] != 0.0
        assert results[1] != 0.0
        assert results[2] != 0.0


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
