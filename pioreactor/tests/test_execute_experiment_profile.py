# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import patch

import pytest
from msgspec.yaml import decode

from pioreactor.actions.leader.experiment_profile import _verify_experiment_profile
from pioreactor.actions.leader.experiment_profile import execute_experiment_profile
from pioreactor.actions.leader.experiment_profile import hours_to_seconds
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


@patch("pioreactor.actions.leader.experiment_profile.get_active_workers_for_experiment")
@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_order(
    mock__load_experiment_profile, mock__get_active_workers_for_experiment
) -> None:
    experiment = "test_execute_experiment_profile_order"

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
    mock__get_active_workers_for_experiment.return_value = ["unit1"]

    actions = []

    def collection_actions(msg):
        actions.append(msg.topic)

    subscribe_and_callback(
        collection_actions,
        [f"pioreactor/unit1/{experiment}/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml", experiment)

    assert actions == [
        f"pioreactor/unit1/{experiment}/run/job1",
        f"pioreactor/unit1/{experiment}/run/job2",
        f"pioreactor/unit1/{experiment}/job2/$state/set",
    ]


@patch("pioreactor.actions.leader.experiment_profile.get_active_workers_for_experiment")
@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_hack_for_led_intensity(
    mock__load_experiment_profile, mock__get_active_workers_for_experiment
) -> None:
    experiment = "test_execute_experiment_profile_hack_for_led_intensity"
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
    mock__get_active_workers_for_experiment.return_value = ["unit1"]

    actions = []

    def collection_actions(msg):
        actions.append((msg.topic, msg.payload.decode()))

    subscribe_and_callback(
        collection_actions,
        [f"pioreactor/unit1/{experiment}/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml", experiment)

    assert actions == [
        (
            f"pioreactor/unit1/{experiment}/run/led_intensity",
            '{"options":{"A":50},"args":[]}',
        ),
        (
            f"pioreactor/unit1/{experiment}/run/led_intensity",
            '{"options":{"A":40,"B":22.5},"args":[]}',
        ),
        (
            f"pioreactor/unit1/{experiment}/run/led_intensity",
            '{"options":{"A":0,"B":0,"C":0,"D":0},"args":[]}',
        ),
    ]


@patch("pioreactor.actions.leader.experiment_profile.get_active_workers_for_experiment")
@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_log_actions(
    mock__load_experiment_profile, mock__get_active_workers_for_experiment
) -> None:
    experiment = "test_execute_experiment_log_actions"
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
    mock__get_active_workers_for_experiment.return_value = ["unit1", "unit2"]

    with collect_all_logs_of_level(
        "NOTICE", "testing_unit", experiment
    ) as notice_bucket, collect_all_logs_of_level(
        "INFO", "testing_unit", experiment
    ) as info_bucket, collect_all_logs_of_level(
        "DEBUG", "testing_unit", experiment
    ) as debug_bucket:
        execute_experiment_profile("profile.yaml", experiment)
        print(notice_bucket)
        assert [log["message"] for log in notice_bucket[1:-1]] == [
            f"test {unit}" for unit in ["unit1", "unit2"]
        ]
        assert [log["message"] for log in info_bucket] == [
            "test job2 on unit1",
        ]
        assert [log["message"] for log in debug_bucket[1:]] == [
            f"test experiment={experiment}",
        ]


@patch("pioreactor.actions.leader.experiment_profile.get_active_workers_for_experiment")
@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_start_and_stop_controller(
    mock__load_experiment_profile, mock__get_active_workers_for_experiment
) -> None:
    experiment = "test_execute_experiment_start_and_stop_controller"
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
    mock__get_active_workers_for_experiment.return_value = ["unit1"]

    execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_update_automations_not_controllers(
    mock__load_experiment_profile,
) -> None:
    experiment = "test_execute_experiment_update_automations_not_controllers"
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
        execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile.get_active_workers_for_experiment")
@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_update_automation(
    mock__load_experiment_profile, mock__get_active_workers_for_experiment
) -> None:
    experiment = "test_execute_experiment_update_automation"
    action1 = Start(
        hours_elapsed=0 / 60 / 60,
        options={"automation_name": "thermostat", "target_temperature": 25},
    )
    action2 = Update(hours_elapsed=1 / 60 / 60, options={"target_temperature": 30})

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
    mock__get_active_workers_for_experiment.return_value = ["unit1"]

    execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_start_controller_and_stop_automation_fails(
    mock__load_experiment_profile,
) -> None:
    experiment = "test_execute_experiment_start_controller_and_stop_automation_fails"
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
        execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_start_automation_fails(
    mock__load_experiment_profile,
) -> None:
    experiment = "test_execute_experiment_start_automation_fails"
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
        execute_experiment_profile("profile.yaml", experiment)


@pytest.mark.xfail(reason="need to write a good test for this")
def test_label_fires_a_relabel_to_leader_endpoint():
    assert False


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_simple_if2(mock__load_experiment_profile) -> None:
    experiment = "test_execute_experiment_profile_simple_if2"
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
        [f"pioreactor/unit1/{experiment}/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml", experiment)

    assert actions == [
        f"pioreactor/unit1/{experiment}/run/jobbing",
    ]


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_simple_if(mock__load_experiment_profile) -> None:
    experiment = "test_execute_experiment_profile_simple_if"
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
        [f"pioreactor/unit1/{experiment}/#"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml", experiment)

    assert actions == [
        f"pioreactor/unit1/{experiment}/run/jobbing",
        f"pioreactor/unit1/{experiment}/run/conditional_jobbing",
    ]


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_expression(mock__load_experiment_profile) -> None:
    experiment = "test_execute_experiment_profile_expression"
    unit = "unit1"
    job_name = "jobbing"
    publish(f"pioreactor/{unit}/{experiment}/{job_name}/target", 10, retain=True)

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
        [f"pioreactor/unit1/{experiment}/run/jobbing"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml", experiment)

    assert actions == ['{"options":{"target":11.0,"dont_eval":"1.0 + 1.0"},"args":[]}']


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_wrong_syntax_in_if_statement(mock__load_experiment_profile) -> None:
    experiment = "test_wrong_syntax_in_if_statement"
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
        execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile.get_active_workers_for_experiment")
@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_repeat_block(mock__load_experiment_profile, mock__get_active_workers_for_experiment) -> None:
    experiment = "test_repeat_block"
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
    mock__get_active_workers_for_experiment.return_value = ["unit1"]

    actions = []

    def collect_actions(msg):
        actions.append(msg.payload.decode())

    subscribe_and_callback(
        collect_actions,
        [f"pioreactor/unit1/{experiment}/jobbing/setting/set"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml", experiment)

    assert actions == ["1"] * repeat_num


@patch("pioreactor.whoami._get_assigned_experiment_name")
@patch("pioreactor.actions.leader.experiment_profile.get_active_workers_for_experiment")
@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_expression_in_common(
    mock__load_experiment_profile, mock__get_active_workers_for_experiment, mock__get_assigned_experiment_name
) -> None:
    experiment = "test_execute_experiment_profile_expression_in_common"
    unit = "unit1"
    job_name = "jobbing"
    publish(f"pioreactor/{unit}/{experiment}/{job_name}/target", 10, retain=True)

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
    mock__get_active_workers_for_experiment.return_value = ["unit1"]
    mock__get_assigned_experiment_name.return_value = experiment

    actions = []

    def collection_actions(msg):
        actions.append(msg.payload.decode())

    subscribe_and_callback(
        collection_actions,
        [f"pioreactor/{unit}/{experiment}/run/jobbing"],
        allow_retained=False,
    )

    execute_experiment_profile("profile.yaml", experiment)

    assert actions == ['{"options":{"target":11.0},"args":[]}']


def test_profiles_in_github_repo() -> None:
    from pioreactor.mureq import get

    # Set the API endpoint URL
    owner = "Pioreactor"
    repo = "experiment_profile_examples"
    path = ""  # Top level directory
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Make a GET request to the GitHub API
    response = get(api_url)
    response.raise_for_status()  # Will raise an HTTPError if the HTTP request returned an unsuccessful status code

    # Check for YAML files
    yaml_files = [file for file in response.json() if file["name"].endswith(".yaml")]

    # Print the list of YAML files
    for file in yaml_files:
        content = get(file["download_url"]).content
        profile = decode(content, type=Profile)
        assert _verify_experiment_profile(profile)
