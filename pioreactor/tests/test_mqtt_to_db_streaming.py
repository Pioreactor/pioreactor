# -*- coding: utf-8 -*-
import sqlite3, time, json
import numpy as np
from pioreactor.config import config
import pioreactor.background_jobs.leader.mqtt_to_db_streaming as m2db
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.utils import local_persistant_storage


def test_kalman_filter_entries():
    config["storage"]["database"] = "test.sqlite"
    config["od_config.od_sampling"]["samples_per_second"] = "0.2"

    unit = "unit"
    exp = "exp"

    def parse_kalman_filter_outputs(topic, payload):
        metadata, _ = m2db.produce_metadata(topic)
        payload = json.loads(payload)
        return {
            "experiment": metadata.experiment,
            "pioreactor_unit": metadata.pioreactor_unit,
            "timestamp": metadata.timestamp,
            "state": json.dumps(payload["state"]),
            "covariance_matrix": json.dumps(payload["covariance_matrix"]),
        }

    # init the database
    connection = sqlite3.connect(config["storage"]["database"])
    cursor = connection.cursor()

    sql_file = open("sql/create_tables.sql")
    sql_as_string = sql_file.read()
    cursor.executescript(sql_as_string)
    connection.commit()

    # turn on data collection
    interval = 0.5
    od = start_od_reading(
        od_angle_channel1="135",
        od_angle_channel2="90",
        sampling_rate=interval,
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

    od.set_state(od.DISCONNECTED)
    gr.set_state(gr.DISCONNECTED)
    m.set_state(m.DISCONNECTED)
