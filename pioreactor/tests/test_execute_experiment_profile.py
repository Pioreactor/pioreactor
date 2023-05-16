# -*- coding: utf-8 -*-
# test_execute_experiment_profile.py
from __future__ import annotations

from unittest.mock import patch

from pioreactor.actions.leader.execute_experiment_profile import execute_experiment_profile
from pioreactor.actions.leader.execute_experiment_profile import hours_to_seconds
from pioreactor.experiment_profiles.profile_struct import Action
from pioreactor.experiment_profiles.profile_struct import Metadata
from pioreactor.experiment_profiles.profile_struct import Plugin
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.pubsub import subscribe_and_callback


# First test the hours_to_seconds function
def test_hours_to_seconds():
    assert hours_to_seconds(1) == 3600
    assert hours_to_seconds(0.5) == 1800
    assert hours_to_seconds(0) == 0


# Test execute_experiment_profile function
@patch("pioreactor.actions.leader.execute_experiment_profile.load_and_verify_profile_file")
def test_execute_experiment_profile_order(mock_load_and_verify_profile_file):
    # Setup some test data
    action1 = Action(type="start", hours_elapsed=0 / 60 / 60)
    action2 = Action(type="start", hours_elapsed=5 / 60 / 60)
    action3 = Action(type="stop", hours_elapsed=10 / 60 / 60)

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[Plugin(name="test_plugin", version="1.0.0")],
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
