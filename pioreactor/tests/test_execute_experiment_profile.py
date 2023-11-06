# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import patch

from pioreactor.actions.leader.experiment_profile import execute_experiment_profile
from pioreactor.actions.leader.experiment_profile import hours_to_seconds
from pioreactor.experiment_profiles.profile_struct import Action
from pioreactor.experiment_profiles.profile_struct import Metadata
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import subscribe_and_callback


# First test the hours_to_seconds function
def test_hours_to_seconds() -> None:
    assert hours_to_seconds(1) == 3600
    assert hours_to_seconds(0.5) == 1800
    assert hours_to_seconds(0) == 0


# Test execute_experiment_profile function
@patch("pioreactor.actions.leader.experiment_profile.load_and_verify_profile_file")
def test_execute_experiment_profile_order(mock_load_and_verify_profile_file) -> None:
    # Setup some test data
    action1 = Action(type="start", hours_elapsed=0 / 60 / 60)
    action2 = Action(type="start", hours_elapsed=5 / 60 / 60)
    action3 = Action(type="stop", hours_elapsed=10 / 60 / 60)

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        common={"job1": {"actions": [action1]}},
        pioreactors={"unit1": {"jobs": {"job2": {"actions": [action2, action3]}}}},
        metadata=Metadata(author="test_author"),
        labels={"unit1": "label1"},
    )

    mock_load_and_verify_profile_file.return_value = profile

    actions = []

    def collection_actions(msg):
        actions.append(msg.topic)

    subscribe_and_callback(
        collection_actions,
        ["pioreactor/unit1/_testing_experiment/#", "pioreactor/$broadcast/_testing_experiment/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml")

    assert actions == [
        "pioreactor/$broadcast/_testing_experiment/run/job1",
        "pioreactor/unit1/_testing_experiment/run/job2",
        "pioreactor/unit1/_testing_experiment/job2/$state/set",
    ]


@patch("pioreactor.actions.leader.experiment_profile.load_and_verify_profile_file")
def test_execute_experiment_profile_hack_for_led_intensity(
    mock_load_and_verify_profile_file,
) -> None:
    # Setup some test data
    action1 = Action(type="start", hours_elapsed=0 / 60 / 60, options={"A": 50})
    action2 = Action(type="update", hours_elapsed=2 / 60 / 60, options={"A": 40, "B": 22.5})
    action3 = Action(type="stop", hours_elapsed=4 / 60 / 60)
    job = "led_intensity"

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        pioreactors={"unit1": {"jobs": {job: {"actions": [action1, action2, action3]}}}},
        metadata=Metadata(author="test_author"),
    )

    mock_load_and_verify_profile_file.return_value = profile

    actions = []

    def collection_actions(msg):
        actions.append((msg.topic, msg.payload.decode()))

    subscribe_and_callback(
        collection_actions,
        ["pioreactor/unit1/_testing_experiment/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml")

    assert actions == [
        (
            "pioreactor/unit1/_testing_experiment/run/led_intensity",
            '{"options":{"A":50},"args":[]}',
        ),
        (
            "pioreactor/unit1/_testing_experiment/run/led_intensity",
            '{"options":{"A":40,"B":22.5},"args":[]}',
        ),
        (
            "pioreactor/unit1/_testing_experiment/run/led_intensity",
            '{"options":{"A":0,"B":0,"C":0,"D":0},"args":[]}',
        ),
    ]


# Test execute_experiment_profile function
@patch("pioreactor.actions.leader.experiment_profile.load_and_verify_profile_file")
def test_execute_experiment_log_actions(mock_load_and_verify_profile_file) -> None:
    # Setup some test data
    action1 = Action(type="log", hours_elapsed=0 / 60 / 60, options={"message": "test {unit}"})
    action2 = Action(
        type="log",
        hours_elapsed=5 / 60 / 60,
        options={"message": "test {job} on {unit}", "level": "INFO"},
    )
    action3 = Action(
        type="log", hours_elapsed=10 / 60 / 60, options={"message": "test {experiment}"}
    )

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        common={"job1": {"actions": [action1]}},
        pioreactors={"unit1": {"jobs": {"job2": {"actions": [action2, action3]}}}},
        metadata=Metadata(author="test_author"),
        labels={"unit1": "label1"},
    )

    mock_load_and_verify_profile_file.return_value = profile

    with collect_all_logs_of_level(
        "NOTICE", "testing_unit", "_testing_experiment"
    ) as notice_bucket, collect_all_logs_of_level(
        "INFO", "testing_unit", "_testing_experiment"
    ) as info_bucket:
        execute_experiment_profile("profile.yaml")

        assert [
            log["message"] for log in notice_bucket[1:-1]
        ] == [  # slice to remove the first and last NOTICE
            "test $broadcast",
            "test _testing_experiment",
        ]
        assert [log["message"] for log in info_bucket] == [
            "test job2 on unit1",
        ]
