# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs.leader.time_series_aggregating import (
    TimeSeriesAggregation,
)
from pioreactor.pubsub import publish
from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT

unit = get_unit_name()
experiment = UNIVERSAL_EXPERIMENT
leader = "leader"


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.75)


def test_subscribe_and_listen_to_clear_simple():
    publish(f"pioreactor/{unit}/{experiment}/growth_rate", None, retain=True)
    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", None, retain=True)
    publish(f"pioreactor/{unit}2/{experiment}/growth_rate", None, retain=True)

    def unit_from_topic(topic):
        return topic.split("/")[1]

    ts = TimeSeriesAggregation(
        f"pioreactor/+/{experiment}/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=leader,
        ignore_cache=True,
        record_every_n_seconds=0.1,
        extract_label=unit_from_topic,
    )

    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.0)
    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.1)
    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.2)
    publish(f"pioreactor/{unit}2/{experiment}/growth_rate", 1.0)
    pause()
    assert ts.aggregated_time_series["series"] == [f"{unit}1", f"{unit}2"]

    publish(
        f"pioreactor/{leader}/{experiment}/time_series_aggregating/aggregated_time_series/set",
        None,
    )
    pause()
    pause()
    pause()
    assert ts.aggregated_time_series["series"] == []


def test_subscribe_and_listen_to_clear_different_formatter():
    def single_sensor_label_from_topic(topic):
        split_topic = topic.split("/")
        return f"{split_topic[1]}-{split_topic[-1]}"

    ts = TimeSeriesAggregation(
        f"pioreactor/+/{experiment}/od_raw/135/+",
        output_dir="./",
        experiment=experiment,
        unit=leader,
        ignore_cache=True,
        record_every_n_seconds=0.1,
        extract_label=single_sensor_label_from_topic,
    )

    publish(f"pioreactor/{unit}1/{experiment}/od_raw/135/0", 1.0)
    publish(f"pioreactor/{unit}1/{experiment}/od_raw/135/0", 1.1)
    publish(f"pioreactor/{unit}1/{experiment}/od_raw/135/1", 1.0)
    publish(f"pioreactor/{unit}2/{experiment}/od_raw/135/0", 1.0)
    pause()
    assert ts.aggregated_time_series["series"] == [
        "testing_unit1-A",
        "testing_unit1-B",
        "testing_unit2-A",
    ]

    publish(
        f"pioreactor/{leader}/{experiment}/time_series_aggregating/aggregated_time_series/set",
        None,
    )
    pause()
    assert ts.aggregated_time_series["series"] == []


def test_time_window_seconds():
    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", None, retain=True)
    publish(f"pioreactor/{unit}2/{experiment}/growth_rate", None, retain=True)
    publish(f"pioreactor/{unit}/{experiment}/growth_rate", None, retain=True)

    def unit_from_topic(topic):
        return topic.split("/")[1]

    ts = TimeSeriesAggregation(
        f"pioreactor/+/{experiment}/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=leader,
        ignore_cache=True,
        extract_label=unit_from_topic,
        record_every_n_seconds=0.1,
        time_window_seconds=5,
    )

    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.1)
    pause()
    assert ts.aggregated_time_series["series"] == ["testing_unit1"]
    assert len(ts.aggregated_time_series["data"][0]) == 1
    time.sleep(10)

    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.2)
    pause()
    assert len(ts.aggregated_time_series["data"][0]) == 1

    publish(
        f"pioreactor/{leader}/{experiment}/time_series_aggregating/aggregated_time_series/set",
        None,
    )
    pause()
    assert ts.aggregated_time_series["series"] == []


def test_every_n_seconds():
    def unit_from_topic(topic):
        return topic.split("/")[1]

    ts = TimeSeriesAggregation(
        f"pioreactor/+/{experiment}/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=leader,
        ignore_cache=True,
        extract_label=unit_from_topic,
        record_every_n_seconds=5,
    )

    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.0)
    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.1)
    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.2)
    pause()
    assert ts.aggregated_time_series["series"] == []
    time.sleep(10)

    assert ts.aggregated_time_series["series"] == [f"{unit}1"]
    assert len(ts.aggregated_time_series["data"][0]) == 1
    time.sleep(3)

    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.3)
    publish(f"pioreactor/{unit}1/{experiment}/growth_rate", 1.4)
    time.sleep(10)
    assert len(ts.aggregated_time_series["data"][0]) == 2

    publish(
        f"pioreactor/{leader}/{experiment}/time_series_aggregating/aggregated_time_series/set",
        None,
    )
    pause()
    assert ts.aggregated_time_series["series"] == []


def test_passes_multiple_experiments_when_allowed():

    publish(f"pioreactor/{unit}/exp1/growth_rate", None, retain=True)
    publish(f"pioreactor/{unit}/exp2/growth_rate", None, retain=True)

    def unit_from_topic(topic):
        return topic.split("/")[1]

    # NOTE: see the +, this is what is used in production
    ts = TimeSeriesAggregation(
        "pioreactor/+/+/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=leader,
        ignore_cache=True,
        extract_label=unit_from_topic,
        record_every_n_seconds=0.1,
    )

    publish(f"pioreactor/{unit}/exp1/growth_rate", 1.0)
    pause()
    publish(f"pioreactor/{unit}/exp2/growth_rate", 1.1)
    pause()
    assert [_["y"] for _ in ts.aggregated_time_series["data"][0]] == [1.0, 1.1]


def test_drops_really_old_data():

    publish(f"pioreactor/{unit}/exp1/growth_rate", None, retain=True)
    publish(f"pioreactor/{unit}/exp2/growth_rate", None, retain=True)

    def unit_from_topic(topic):
        return topic.split("/")[1]

    # NOTE: see the +, this is what is used in production
    ts = TimeSeriesAggregation(
        "pioreactor/+/+/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=leader,
        ignore_cache=True,
        extract_label=unit_from_topic,
        record_every_n_seconds=0.1,
        time_window_seconds=3,
    )

    publish(f"pioreactor/{unit}/exp1/growth_rate", 1.0)
    pause()
    publish(f"pioreactor/{unit}/exp1/growth_rate", 1.1)
    pause()
    assert len(ts.aggregated_time_series["data"][0]) > 0

    pause()
    pause()
    pause()
    pause()
    assert len(ts.aggregated_time_series["data"][0]) == 0


def test_drops_retained_messages():

    publish(f"pioreactor/{unit}/exp1/growth_rate", None, retain=True)
    publish(f"pioreactor/{unit}/exp2/growth_rate", None, retain=True)

    def unit_from_topic(topic):
        return topic.split("/")[1]

    publish(f"pioreactor/{unit}/exp2/growth_rate", 0.9, retain=True)

    # NOTE: see the +, this is what is used in production
    ts = TimeSeriesAggregation(
        "pioreactor/+/+/growth_rate",
        output_dir="./",
        experiment=experiment,
        unit=leader,
        ignore_cache=True,
        extract_label=unit_from_topic,
        record_every_n_seconds=0.1,
    )
    pause()
    pause()
    pause()
    publish(f"pioreactor/{unit}/exp2/growth_rate", 1.0, retain=True)
    pause()
    publish(f"pioreactor/{unit}/exp2/growth_rate", 1.1, retain=True)
    pause()
    assert [_["y"] for _ in ts.aggregated_time_series["data"][0]] == [1.0, 1.1]
