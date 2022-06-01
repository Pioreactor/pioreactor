# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import time

import pioreactor.background_jobs.leader.mqtt_to_db_streaming as m2db
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.config import config
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.utils import local_persistant_storage


def test_kalman_filter_entries() -> None:
    config["storage"]["database"] = "test.sqlite"
    config["od_config"]["samples_per_second"] = "0.2"
    config["od_config.photodiode_channel"]["1"] = "135"
    config["od_config.photodiode_channel"]["2"] = "90"

    unit = "unit"
    exp = "test_kalman_filter_entries"

    def parse_kalman_filter_outputs(topic: str, payload) -> dict:
        metadata = m2db.produce_metadata(topic)
        payload_dict = json.loads(payload)
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

    # init the database
    connection = sqlite3.connect(config["storage"]["database"])
    cursor = connection.cursor()

    cursor.executescript(
        """
DROP TABLE kalman_filter_outputs;

CREATE TABLE IF NOT EXISTS kalman_filter_outputs (
    timestamp                TEXT NOT NULL,
    pioreactor_unit          TEXT NOT NULL,
    experiment               TEXT NOT NULL,
    state_0                  REAL NOT NULL,
    state_1                  REAL NOT NULL,
    state_2                  REAL NOT NULL,
    cov_00                   REAL NOT NULL,
    cov_01                   REAL NOT NULL,
    cov_02                   REAL NOT NULL,
    cov_11                   REAL NOT NULL,
    cov_12                   REAL NOT NULL,
    cov_22                   REAL NOT NULL
);

    """
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
            parse_kalman_filter_outputs,
            "kalman_filter_outputs",
        )
    ]

    m = m2db.MqttToDBStreamer(parsers, unit=unit, experiment=exp)

    # let data collect
    time.sleep(10)

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
        published_settings = {
            "some_key": {
                "datatype": "json",
                "settable": False,
            },
        }

        def __init__(self, unit, experiment) -> None:
            super(TestJob, self).__init__(job_name="test_job", unit=unit, experiment=experiment)
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
            time.sleep(1)

        assert len(bucket) == 0
