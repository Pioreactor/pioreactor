# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
from time import sleep

from msgspec.json import encode

import pioreactor.background_jobs.leader.mqtt_to_db_streaming as m2db
from pioreactor import mureq
from pioreactor import structs
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.config import config
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.utils import local_persistant_storage
from pioreactor.whoami import get_unit_name


def test_updated_heater_dc():
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

    with m2db.MqttToDBStreamer(parsers, unit=unit, experiment=exp):
        sleep(1)
        publish(
            f"pioreactor/{unit}/test/temperature_automation/latest_event",
            '{"event_name":"UpdatedHeaterDC","message":"delta_dc=3.28125","data":{"current_dc":null,"delta_dc":3.28125}}',
        )
        sleep(5)

    cursor.execute("SELECT * FROM temperature_automation_events WHERE pioreactor_unit=?", (unit,))
    results = cursor.fetchall()
    assert len(results) == 1


def test_calibration_gets_saved() -> None:
    experiment = "test_calibration_gets_saved"
    config["storage"]["database"] = "test.sqlite"

    # init the database
    connection = sqlite3.connect(config["storage"]["database"])
    cursor = connection.cursor()

    cursor.executescript("DROP TABLE IF EXISTS calibrations;")
    cursor.executescript(
        mureq.get(
            "https://raw.githubusercontent.com/Pioreactor/CustoPiZer/pioreactor/workspace/scripts/files/sql/create_tables.sql"
        ).content.decode("utf-8")
    )
    connection.commit()

    parsers = [
        m2db.TopicToParserToTable(
            "pioreactor/+/+/calibrations",
            m2db.parse_calibrations,
            "calibrations",
        )
    ]

    with m2db.MqttToDBStreamer(parsers, unit=get_unit_name(), experiment=experiment):
        sleep(1)
        publish(
            f"pioreactor/{get_unit_name()}/test/calibrations",
            encode(
                structs.WastePumpCalibration(
                    name="test",
                    timestamp="2012-01-01",
                    pump="waste",
                    hz=120,
                    dc=60.0,
                    duration_=1.0,
                    bias_=0.0,
                    voltage=12.0,
                )
            ),
        )
        sleep(1)

        cursor.execute("SELECT * FROM calibrations WHERE pioreactor_unit=?", (get_unit_name(),))
        results = cursor.fetchall()
        assert len(results) == 1

        # create some new calibration, like from a plugin
        class LEDCalibration(structs.Calibration, tag="led"):  # type: ignore
            timestamp: str

        publish(
            f"pioreactor/{get_unit_name()}/test/calibrations",
            encode(
                LEDCalibration(
                    timestamp="2012-01-02",
                )
            ),
        )
        sleep(1)

        cursor.execute(
            "SELECT * FROM calibrations WHERE pioreactor_unit=? ORDER BY created_at",
            (get_unit_name(),),
        )
        results = cursor.fetchall()
        assert len(results) == 2
        assert results[1][2] == "led"


def test_kalman_filter_entries() -> None:
    config["storage"]["database"] = "test.sqlite"
    config["od_config"]["samples_per_second"] = "0.2"
    config["od_config.photodiode_channel"]["1"] = "135"
    config["od_config.photodiode_channel"]["2"] = "90"

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

    # turn on data collection
    interval = 0.5
    od = start_od_reading(
        od_angle_channel1="135",
        od_angle_channel2="90",
        interval=interval,
        fake_data=True,
        unit=unit,
        experiment=exp,
        use_calibration=False,
    )

    with local_persistant_storage("od_normalization_mean") as cache:
        cache[exp] = json.dumps({"1": 0.5, "2": 0.8})

    with local_persistant_storage("od_normalization_variance") as cache:
        cache[exp] = json.dumps({"1": 1e-6, "2": 1e-4})

    gr = GrowthRateCalculator(unit=unit, experiment=exp)

    # turn on our mqtt to db
    parsers = [
        m2db.TopicToParserToTable(
            "pioreactor/+/+/growth_rate_calculating/kalman_filter_outputs",
            m2db.parse_kalman_filter_outputs,
            "kalman_filter_outputs",
        )
    ]

    m = m2db.MqttToDBStreamer(parsers, unit=unit, experiment=exp)

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

    od.clean_up()
    gr.clean_up()
    m.clean_up()


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
            self.some_key = {"int": 4, "ts": 1}

    def parse_setting(topic, payload) -> dict:
        return json.loads(payload)

    # turn on our mqtt to db
    parsers = [
        m2db.TopicToParserToTable(
            "pioreactor/+/+/test_job/some_key",
            parse_setting,
            "table_setting",
        )
    ]

    with m2db.MqttToDBStreamer(parsers, unit=unit, experiment=exp):
        with collect_all_logs_of_level("ERROR", unit, exp) as bucket:
            t = TestJob(unit=unit, experiment=exp)
            t.clean_up()
            sleep(1)

        assert len(bucket) == 0
