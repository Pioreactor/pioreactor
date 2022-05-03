# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import time

import numpy as np

import pioreactor.background_jobs.leader.mqtt_to_db_streaming as m2db
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.config import config
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.timing import current_utc_time


def test_kalman_filter_entries() -> None:
    config["storage"]["database"] = "test.sqlite"
    config["od_config"]["samples_per_second"] = "0.2"
    config["od_config.photodiode_channel"]["1"] = "135"
    config["od_config.photodiode_channel"]["2"] = "90"

    unit = "unit"
    exp = "test_kalman_filter_entries"

    def parse_kalman_filter_outputs(topic, payload) -> dict:
        metadata, _ = m2db.produce_metadata(topic)
        payload = json.loads(payload)
        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": current_utc_time(),
            "state": json.dumps(payload["state"]),
            "covariance_matrix": json.dumps(payload["covariance_matrix"]),
        }

    # init the database
    connection = sqlite3.connect(config["storage"]["database"])
    cursor = connection.cursor()

    cursor.executescript(
        """
CREATE TABLE IF NOT EXISTS kalman_filter_outputs (
    timestamp                TEXT NOT NULL,
    pioreactor_unit          TEXT NOT NULL,
    experiment               TEXT NOT NULL,
    state                    TEXT NOT NULL,
    covariance_matrix        TEXT NOT NULL
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
        'SELECT json_array_length("state"), json_array_length("covariance_matrix"), json("covariance_matrix") FROM kalman_filter_outputs WHERE experiment = ? ORDER BY timestamp DESC LIMIT 1',
        (exp,),
    )
    results = cursor.fetchone()
    assert (
        results[0] == 3
    )  # why 3? growth rate, od filtered, and acceleration are the three hidden states
    assert results[1] == 3
    assert np.array(json.loads(results[2])).shape == (3, 3)

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
            super(TestJob, self).__init__(
                job_name="test_job", unit=unit, experiment=experiment
            )
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
