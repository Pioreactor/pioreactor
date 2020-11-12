# -*- coding: utf-8 -*-
import pytest
import time
from morbidostat.background_jobs.leader_jobs.time_series_aggregating import TimeSeriesAggregation
from morbidostat.pubsub import publish
from morbidostat.whoami import unit, experiment


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.75)


def test_subscribe_and_listen_to_clear():
    def unit_from_topic(topic):
        return topic.split("/")[1]

    ts = TimeSeriesAggregation(
        f"morbidostat/+/{experiment}/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=unit,
        verbose=0,
        skip_cache=True,
        extract_label=unit_from_topic,
    )

    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.0)
    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.1)
    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.2)
    publish(f"morbidostat/{unit}2/{experiment}/growth_rate", 1.0)
    pause()
    assert ts.aggregated_time_series["series"] == ["_testing_unit1", "_testing_unit2"]

    publish(f"morbidostat/{unit}/{experiment}/time_series_aggregating/aggregated_time_series/set", None)
    pause()
    assert ts.aggregated_time_series["series"] == []


def test_subscribe_and_listen_to_clear2():
    def single_sensor_label_from_topic(topic):
        split_topic = topic.split("/")
        return f"{split_topic[1]}-{split_topic[-1]}"

    ts = TimeSeriesAggregation(
        f"morbidostat/+/{experiment}/od_raw/135/+",
        output_dir="./",
        experiment=experiment,
        unit=unit,
        verbose=0,
        skip_cache=True,
        extract_label=single_sensor_label_from_topic,
    )

    publish(f"morbidostat/{unit}1/{experiment}/od_raw/135/A", 1.0)
    publish(f"morbidostat/{unit}1/{experiment}/od_raw/135/A", 1.1)
    publish(f"morbidostat/{unit}1/{experiment}/od_raw/135/B", 1.0)
    publish(f"morbidostat/{unit}2/{experiment}/od_raw/135/A", 1.0)
    pause()
    assert ts.aggregated_time_series["series"] == ["_testing_unit1-A", "_testing_unit1-B", "_testing_unit2-A"]

    publish(f"morbidostat/{unit}/{experiment}/time_series_aggregating/aggregated_time_series/set", None)
    pause()
    assert ts.aggregated_time_series["series"] == []


def test_time_window_minutes():
    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", None, retain=True)
    publish(f"morbidostat/{unit}2/{experiment}/growth_rate", None, retain=True)
    publish(f"morbidostat/{unit}/{experiment}/growth_rate", None, retain=True)

    def unit_from_topic(topic):
        return topic.split("/")[1]

    ts = TimeSeriesAggregation(
        f"morbidostat/+/{experiment}/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=unit,
        verbose=0,
        skip_cache=True,
        extract_label=unit_from_topic,
        time_window_minutes=5 / 60,
    )

    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.0)
    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.1)
    pause()
    assert ts.aggregated_time_series["series"] == ["_testing_unit1"]
    assert len(ts.aggregated_time_series["data"][0]) == 2
    time.sleep(10)

    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.2)
    pause()
    assert len(ts.aggregated_time_series["data"][0]) == 1

    publish(f"morbidostat/{unit}/{experiment}/time_series_aggregating/aggregated_time_series/set", None)
    pause()
    assert ts.aggregated_time_series["series"] == []


def test_every_n_minutes():
    def unit_from_topic(topic):
        return topic.split("/")[1]

    ts = TimeSeriesAggregation(
        f"morbidostat/+/{experiment}/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=unit,
        verbose=0,
        skip_cache=True,
        extract_label=unit_from_topic,
        every_n_minutes=5 / 60,
    )

    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.0)
    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.1)
    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.2)
    pause()
    assert ts.aggregated_time_series["series"] == ["_testing_unit1"]
    assert len(ts.aggregated_time_series["data"][0]) == 0
    time.sleep(10)

    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.3)
    publish(f"morbidostat/{unit}1/{experiment}/growth_rate", 1.4)
    pause()
    assert len(ts.aggregated_time_series["data"][0]) == 1

    publish(f"morbidostat/{unit}/{experiment}/time_series_aggregating/aggregated_time_series/set", None)
    pause()
    assert ts.aggregated_time_series["series"] == []
