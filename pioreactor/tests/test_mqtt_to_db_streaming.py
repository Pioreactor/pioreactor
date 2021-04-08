# -*- coding: utf-8 -*-
import sqlite3, time, json
import numpy as np
from pioreactor.config import config
import pioreactor.background_jobs.leader.mqtt_to_db_streaming as m2db
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator


def test_kalman_filter_entries():
    config["storage"]["database"] = "test.sqlite"
    config["od_config.od_sampling"]["samples_per_second"] = "0.2"

    unit = "unit"
    exp = "exp"

    # init the database
    connection = sqlite3.connect(config["storage"]["database"])
    cursor = connection.cursor()

    sql_file = open("sql/create_tables.sql")
    sql_as_string = sql_file.read()
    cursor.executescript(sql_as_string)
    connection.commit()

    # turn on data collection
    interval = 0.5
    ODReader(
        channel_label_map={"A0": "135/0", "A1": "90/1"},
        sampling_rate=interval,
        unit=unit,
        experiment=exp,
        fake_data=True,
    )
    GrowthRateCalculator(unit=unit, experiment=exp)

    # turn on our mqtt to db
    parsers = [
        m2db.Metadata(
            "pioreactor/+/+/growth_rate_calculating/kalman_filter_outputs",
            "kalman_filter_outputs",
            m2db.parse_kalman_filter_outputs,
        )
    ]

    m2db.MqttToDBStreamer(parsers, unit=unit, experiment=exp)

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
    assert results[0] == 4
    assert results[1] == 4
    assert np.array(json.loads(results[2])).shape == (4, 4)
