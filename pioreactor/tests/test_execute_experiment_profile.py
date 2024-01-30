# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import patch

import pytest

from pioreactor.actions.leader.experiment_profile import execute_experiment_profile
from pioreactor.actions.leader.experiment_profile import hours_to_seconds
from pioreactor.config import get_active_workers_in_inventory
from pioreactor.experiment_profiles.profile_struct import _LogOptions
from pioreactor.experiment_profiles.profile_struct import CommonBlock
from pioreactor.experiment_profiles.profile_struct import Job
from pioreactor.experiment_profiles.profile_struct import Log
from pioreactor.experiment_profiles.profile_struct import Metadata
from pioreactor.experiment_profiles.profile_struct import PioreactorSpecificBlock
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.experiment_profiles.profile_struct import Repeat
from pioreactor.experiment_profiles.profile_struct import Start
from pioreactor.experiment_profiles.profile_struct import Stop
from pioreactor.experiment_profiles.profile_struct import Update
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe_and_callback


# First test the hours_to_seconds function
def test_hours_to_seconds() -> None:
    assert hours_to_seconds(1) == 3600
    assert hours_to_seconds(0.5) == 1800
    assert hours_to_seconds(0) == 0


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_order(mock__load_experiment_profile) -> None:
    action1 = Start(hours_elapsed=0 / 60 / 60)
    action2 = Start(hours_elapsed=2 / 60 / 60)
    action3 = Stop(hours_elapsed=4 / 60 / 60)

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        common=CommonBlock(jobs={"job1": Job(actions=[action1])}),
        pioreactors={
            "unit1": PioreactorSpecificBlock(jobs={"job2": Job(actions=[action2, action3])}, label="label1"),
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    actions = []

    def collection_actions(msg):
        actions.append(msg.topic)

    subscribe_and_callback(
        collection_actions,
        ["pioreactor/unit1/_testing_experiment/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml")

    assert actions == [
        "pioreactor/unit1/_testing_experiment/run/job2",
        "pioreactor/unit1/_testing_experiment/job2/$state/set",
    ]


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_hack_for_led_intensity(
    mock__load_experiment_profile,
) -> None:
    action1 = Start(hours_elapsed=0 / 60 / 60, options={"A": 50})
    action2 = Update(hours_elapsed=1 / 60 / 60, options={"A": 40, "B": 22.5})
    action3 = Stop(hours_elapsed=2 / 60 / 60)
    job = "led_intensity"

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        pioreactors={"unit1": PioreactorSpecificBlock(jobs={job: Job(actions=[action1, action2, action3])})},
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

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


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_log_actions(mock__load_experiment_profile) -> None:
    action1 = Log(hours_elapsed=0 / 60 / 60, options=_LogOptions(message="test {unit}"))
    action2 = Log(
        hours_elapsed=2 / 60 / 60, options=_LogOptions(message="test {job} on {unit}", level="INFO")
    )
    action3 = Log(
        hours_elapsed=4 / 60 / 60, options=_LogOptions(message="test experiment={experiment}", level="DEBUG")
    )

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        common=CommonBlock(jobs={"job1": Job(actions=[action1])}),
        pioreactors={
            "unit1": PioreactorSpecificBlock(jobs={"job2": Job(actions=[action2, action3])}, label="label1")
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    with collect_all_logs_of_level(
        "NOTICE", "testing_unit", "_testing_experiment"
    ) as notice_bucket, collect_all_logs_of_level(
        "INFO", "testing_unit", "_testing_experiment"
    ) as info_bucket, collect_all_logs_of_level(
        "DEBUG", "testing_unit", "_testing_experiment"
    ) as debug_bucket:
        execute_experiment_profile("profile.yaml")

        assert [log["message"] for log in notice_bucket[1:-1]] == [
            f"test {unit}" for unit in get_active_workers_in_inventory()
        ]
        assert [log["message"] for log in info_bucket] == [
            "test job2 on unit1",
        ]
        assert [log["message"] for log in debug_bucket[1:]] == [
            "test experiment=_testing_experiment",
        ]


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_start_and_stop_controller(mock__load_experiment_profile) -> None:
    action1 = Start(hours_elapsed=0 / 60 / 60, options={"automation_name": "silent"})
    action2 = Stop(
        hours_elapsed=1 / 60 / 60,
    )

    profile = Profile(
        experiment_profile_name="test_profile",
        common=CommonBlock(jobs={"temperature_control": Job(actions=[action1, action2])}),
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    execute_experiment_profile("profile.yaml")


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_update_automations_not_controllers(
    mock__load_experiment_profile,
) -> None:
    action1 = Start(
        hours_elapsed=0 / 60 / 60,
        options={"automation_name": "thermostat", "target_temperature": 25},
    )
    action2 = Update(hours_elapsed=1 / 60 / 60, options={"target_temperature": 30})

    profile = Profile(
        experiment_profile_name="test_profile",
        common=CommonBlock(jobs={"temperature_control": Job(actions=[action1, action2])}),
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    with pytest.raises(ValueError, match="Update"):
        execute_experiment_profile("profile.yaml")


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_start_controller_and_stop_automation_fails(
    mock__load_experiment_profile,
) -> None:
    action1 = Start(hours_elapsed=0 / 60 / 60, options={"automation_name": "silent"})
    action2 = Stop(
        hours_elapsed=1 / 60 / 60,
    )

    profile = Profile(
        experiment_profile_name="test_profile",
        common=CommonBlock(
            jobs={
                "temperature_control": Job(actions=[action1]),
                "temperature_automation": Job(actions=[action2]),
            }
        ),
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    with pytest.raises(ValueError, match="stop"):
        execute_experiment_profile("profile.yaml")


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_start_automation_fails(
    mock__load_experiment_profile,
) -> None:
    action = Start(hours_elapsed=0 / 60 / 60, options={"target_temperature": 20})

    profile = Profile(
        experiment_profile_name="test_profile",
        common=CommonBlock(
            jobs={
                "temperature_automation": Job(actions=[action]),
            }
        ),
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    with pytest.raises(ValueError, match="start"):
        execute_experiment_profile("profile.yaml")


@pytest.mark.xfail(reason="need to write a good test for this")
def test_label_fires_a_relabel_to_leader_endpoint():
    assert False


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_simple_if2(mock__load_experiment_profile) -> None:
    action_true = Start(hours_elapsed=0, if_="${{1 == 1}}")

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={
                    "jobbing": Job(actions=[action_true]),
                }
            ),
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    actions = []

    def collection_actions(msg):
        actions.append(msg.topic)

    subscribe_and_callback(
        collection_actions,
        ["pioreactor/unit1/_testing_experiment/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml")

    assert actions == [
        "pioreactor/unit1/_testing_experiment/run/jobbing",
    ]


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_simple_if(mock__load_experiment_profile) -> None:
    action_true = Start(hours_elapsed=0, if_="1 == 1")
    action_false = Start(hours_elapsed=0, if_="False")
    action_true_conditional = Start(hours_elapsed=1 / 60 / 60, if_="(1 >= 0) and (0 <= 1)")

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={
                    "jobbing": Job(actions=[action_true]),
                    "not_jobbing": Job(actions=[action_false]),
                    "conditional_jobbing": Job(actions=[action_true_conditional]),
                }
            ),
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    actions = []

    def collection_actions(msg):
        actions.append(msg.topic)

    subscribe_and_callback(
        collection_actions,
        ["pioreactor/unit1/_testing_experiment/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml")

    assert actions == [
        "pioreactor/unit1/_testing_experiment/run/jobbing",
        "pioreactor/unit1/_testing_experiment/run/conditional_jobbing",
    ]


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_expression(mock__load_experiment_profile) -> None:
    unit = "unit1"
    job_name = "jobbing"
    publish(f"pioreactor/{unit}/_testing_experiment/{job_name}/target", 10, retain=True)

    action = Start(
        hours_elapsed=0, options={"target": "${{unit1:jobbing:target + 1}}", "dont_eval": "1.0 + 1.0"}
    )

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        pioreactors={
            unit: PioreactorSpecificBlock(
                jobs={
                    job_name: Job(actions=[action]),
                }
            ),
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    actions = []

    def collection_actions(msg):
        actions.append(msg.payload.decode())

    subscribe_and_callback(
        collection_actions,
        ["pioreactor/unit1/_testing_experiment/run/jobbing"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml")

    assert actions == ['{"options":{"target":11.0,"dont_eval":"1.0 + 1.0"},"args":[]}']


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_wrong_syntax_in_if_statement(mock__load_experiment_profile) -> None:
    action = Start(hours_elapsed=0, if_="1 % 1 and ")

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={
                    "jobbing": Job(actions=[action]),
                }
            ),
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    with pytest.raises(SyntaxError):
        execute_experiment_profile("profile.yaml")


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_repeat_block(mock__load_experiment_profile) -> None:
    repeat_num = 6
    repeat_every_hours = 0.001
    start = Start(hours_elapsed=0)
    repeat = Repeat(
        hours_elapsed=0,
        if_="1 > 0",
        repeat_every_hours=repeat_every_hours,
        max_hours=repeat_every_hours * repeat_num,
        actions=[Update(hours_elapsed=0.0, options={"setting": "1"})],
    )

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={
                    "jobbing": Job(actions=[start, repeat]),
                }
            ),
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    actions = []

    def collect_actions(msg):
        actions.append(msg.payload.decode())

    subscribe_and_callback(
        collect_actions,
        ["pioreactor/unit1/_testing_experiment/jobbing/setting/set"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml")

    assert actions == ["1"] * repeat_num


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_expression_in_common(mock__load_experiment_profile) -> None:
    unit = get_active_workers_in_inventory()[0]
    job_name = "jobbing"
    publish(f"pioreactor/{unit}/_testing_experiment/{job_name}/target", 10, retain=True)

    action = Start(
        hours_elapsed=0, options={"target": "${{::jobbing:target + 1}}"}, if_="::jobbing:target > 0"
    )

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        common=CommonBlock(
            jobs={
                job_name: Job(actions=[action]),
            }
        ),
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    actions = []

    def collection_actions(msg):
        actions.append(msg.payload.decode())

    subscribe_and_callback(
        collection_actions,
        [f"pioreactor/{unit}/_testing_experiment/run/jobbing"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml")

    assert actions == ['{"options":{"target":11.0},"args":[]}']
