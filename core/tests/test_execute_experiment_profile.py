# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from msgspec.json import encode
from msgspec.yaml import decode
from pioreactor.actions.leader.experiment_profile import _verify_experiment_profile
from pioreactor.actions.leader.experiment_profile import execute_experiment_profile
from pioreactor.actions.leader.experiment_profile import hours_to_seconds
from pioreactor.actions.leader.experiment_profile import seconds_to_hours
from pioreactor.actions.leader.experiment_profile import time_to_seconds
from pioreactor.background_jobs.stirring import start_stirring
from pioreactor.experiment_profiles.profile_struct import _LogOptions
from pioreactor.experiment_profiles.profile_struct import CommonBlock
from pioreactor.experiment_profiles.profile_struct import Job
from pioreactor.experiment_profiles.profile_struct import Log
from pioreactor.experiment_profiles.profile_struct import Metadata
from pioreactor.experiment_profiles.profile_struct import PioreactorSpecificBlock
from pioreactor.experiment_profiles.profile_struct import Plugin
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.experiment_profiles.profile_struct import Repeat
from pioreactor.experiment_profiles.profile_struct import Start
from pioreactor.experiment_profiles.profile_struct import Stop
from pioreactor.experiment_profiles.profile_struct import Update
from pioreactor.experiment_profiles.profile_struct import When
from pioreactor.mureq import HTTPErrorStatus
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.structs import RawODReading
from pioreactor.utils.timing import current_utc_datetime
from tests.conftest import capture_requests


def test_hours_to_seconds() -> None:
    assert hours_to_seconds(1) == 3600
    assert hours_to_seconds(0.5) == 1800
    assert hours_to_seconds(0) == 0


def test_seconds_to_hours() -> None:
    assert seconds_to_hours(3600.0) == 1
    assert seconds_to_hours(3600) == 1
    assert seconds_to_hours(0) == 0


def test_time_to_seconds_accepts_literals() -> None:
    assert time_to_seconds(0.5) == 1800
    assert time_to_seconds("10s") == 10.0
    assert time_to_seconds("2m") == 120.0
    assert time_to_seconds("1.5h") == 5400.0
    assert time_to_seconds("2d") == 172800.0


def test_time_to_seconds_rejects_bad_literals() -> None:
    with pytest.raises(ValueError):
        time_to_seconds("1 h")

    with pytest.raises(ValueError):
        time_to_seconds("bad")

    with pytest.raises(ValueError):
        time_to_seconds("-5m")


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_order(
    mock__load_experiment_profile,
) -> None:
    experiment = "_testing_experiment"

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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert bucket[0].path == "/api/experiments/_testing_experiment/unit_labels"
    assert bucket[0].json == {"label": "label1", "unit": "unit1"}
    assert bucket[1].path == "/unit_api/jobs/run/job_name/job1"
    assert bucket[2].path == "/unit_api/jobs/run/job_name/job1"
    assert bucket[3].path == "/unit_api/jobs/run/job_name/job2"
    assert bucket[4].path == "/api/workers/unit1/jobs/stop/job_name/job2/experiments/_testing_experiment"


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_hack_for_led_intensity(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert bucket[0].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/led_intensity"
    assert bucket[0].json == {
        "options": {"A": 50},
        "args": [],
        "env": {"JOB_SOURCE": "experiment_profile/1", "EXPERIMENT": "_testing_experiment"},
        "config_overrides": [],
    }

    assert bucket[1].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/led_intensity"
    assert bucket[1].json == {
        "options": {"A": 40, "B": 22.5},
        "args": [],
        "env": {"JOB_SOURCE": "experiment_profile/1", "EXPERIMENT": "_testing_experiment"},
        "config_overrides": [],
    }

    assert bucket[2].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/led_intensity"
    assert bucket[2].json == {
        "options": {"A": 0, "B": 0, "C": 0, "D": 0},
        "env": {"JOB_SOURCE": "experiment_profile/1", "EXPERIMENT": "_testing_experiment"},
        "args": [],
        "config_overrides": [],
    }


@pytest.mark.skipif(os.getenv("GITHUB_ACTIONS") == "true", reason="flakey test in CI???")
@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_log_actions(mock__load_experiment_profile, active_workers_in_cluster) -> None:
    experiment = "_testing_experiment"

    action1 = Log(hours_elapsed=0 / 60 / 60, options=_LogOptions(message=r"test ${{unit()}}"))
    action2 = Log(
        hours_elapsed=2 / 60 / 60,
        options=_LogOptions(message=r"test ${{job_name()}} on ${{unit()}}", level="INFO"),
    )
    action3 = Log(
        hours_elapsed=4 / 60 / 60,
        options=_LogOptions(message=r"test experiment=${{experiment()}}", level="DEBUG"),
    )

    unit = "unit1"
    job_name = "job2"
    publish(f"pioreactor/{unit}/{experiment}/{job_name}/target", 10.5, retain=True)

    action4 = Log(
        hours_elapsed=4 / 60 / 60,
        options=_LogOptions(message=r"dynamic data looks like ${{unit1:job2:target}}", level="DEBUG"),
    )

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        common=CommonBlock(jobs={"job1": Job(actions=[action1])}),
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={"job2": Job(actions=[action2, action3, action4])}, label="label1"
            )
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    with collect_all_logs_of_level("NOTICE", "unit1", experiment) as notice_bucket, collect_all_logs_of_level(
        "INFO", "unit1", experiment
    ) as info_bucket, collect_all_logs_of_level("DEBUG", "unit1", experiment) as debug_bucket:
        execute_experiment_profile("profile.yaml", experiment)
        assert notice_bucket[0]["message"] == "test unit1"
        assert [log["message"] for log in info_bucket[:1]] == [
            "test job2 on unit1",
        ]
        assert [log["message"] for log in debug_bucket] == [
            f"test experiment={experiment}",
            "dynamic data looks like 10.5",
        ]


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_start_and_stop_automations(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
    action1 = Start(hours_elapsed=0 / 60 / 60, options={"automation_name": "silent"})
    action2 = Stop(hours_elapsed=1 / 60 / 60)

    profile = Profile(
        experiment_profile_name="test_profile",
        common=CommonBlock(jobs={"temperature_automation": Job(actions=[action1, action2])}),
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_update_automation(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
    action1 = Start(
        hours_elapsed=0 / 60 / 60,
        options={"automation_name": "thermostat", "target_temperature": 25},
    )
    action2 = Update(hours_elapsed=1 / 60 / 60, options={"target_temperature": 30})

    profile = Profile(
        experiment_profile_name="test_profile",
        common=CommonBlock(
            jobs={
                "temperature_automation": Job(actions=[action1, action2]),
            }
        ),
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_start_automation_succeeds(
    mock__load_experiment_profile,
) -> None:
    experiment = "_testing_experiment"
    start = Start(hours_elapsed=0 / 60 / 60, options={"target_temperature": 20})
    stop = Stop(hours_elapsed=2 / 60 / 60)

    profile = Profile(
        experiment_profile_name="test_profile",
        common=CommonBlock(
            jobs={
                "temperature_automation": Job(actions=[start, stop]),
            }
        ),
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_label_fires_a_relabel_to_leader_endpoint(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"

    profile = Profile(
        experiment_profile_name="test_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(label="label1"),
            "unit2": PioreactorSpecificBlock(label="label2"),
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert bucket[0].path == "/api/experiments/_testing_experiment/unit_labels"
    assert bucket[0].json == {"label": "label1", "unit": "unit1"}
    assert bucket[1].json == {"label": "label2", "unit": "unit2"}


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_simple_if2(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert len(bucket) == 1
    assert bucket[0].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/jobbing"


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_with_unit_function(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
    action_true = Start(hours_elapsed=0, if_="${{ unit() == unit1 }}")

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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert len(bucket) == 1
    assert bucket[0].path == "/unit_api/jobs/run/job_name/jobbing"

    action_true = Start(hours_elapsed=0, if_="${{ unit() == unit2 }}")

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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert len(bucket) == 0


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_simple_if(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert len(bucket) == 2
    assert bucket[0].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/jobbing"
    assert bucket[1].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/conditional_jobbing"


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_expression(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert bucket[0].json == {
        "options": {"target": 11.0, "dont_eval": "1.0 + 1.0"},
        "env": {"EXPERIMENT": "_testing_experiment", "JOB_SOURCE": "experiment_profile/1"},
        "args": [],
        "config_overrides": [],
    }


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_wrong_syntax_in_if_statement(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", "_testing_experiment")

    r = [
        b.json["settings"]["setting"]
        for b in bucket
        if b.path == "/api/workers/unit1/jobs/update/job_name/jobbing/experiments/_testing_experiment"
    ]
    assert r == ["1"] * repeat_num


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_repeat_respects_every_and_time_literals(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"

    start = Start(t="0s")
    repeat = Repeat(
        t="0s",
        every="0.01s",
        max_time="0.03s",
        actions=[Update(t="0s", options={"setting": "1"})],
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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    updates = [
        b
        for b in bucket
        if b.path == "/api/workers/unit1/jobs/update/job_name/jobbing/experiments/_testing_experiment"
    ]

    assert len(updates) == 3


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_repeat_warns_and_skips_actions_beyond_every(mock__load_experiment_profile, caplog) -> None:
    experiment = "_testing_experiment"

    start = Start(t="0s")
    repeat = Repeat(
        t="0s",
        every="0.01s",
        max_time="0.02s",
        actions=[Update(t="0.05s", options={"setting": "1"})],
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

    with caplog.at_level("WARNING"):
        with capture_requests() as bucket:
            execute_experiment_profile("profile.yaml", experiment)

    updates = [
        b
        for b in bucket
        if b.path == "/api/workers/unit1/jobs/update/job_name/jobbing/experiments/_testing_experiment"
    ]

    assert updates == []
    assert any("can't ever run" in record.message for record in caplog.records)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_expression_in_common(
    mock__load_experiment_profile, active_workers_in_cluster
) -> None:
    job_name = "jobbing"

    for worker in active_workers_in_cluster:
        publish(f"pioreactor/{worker}/_testing_experiment/{job_name}/target", 10, retain=True)

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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", "_testing_experiment")

    assert len(bucket) == len(active_workers_in_cluster)
    for item in bucket:
        assert item.json == {
            "args": [],
            "env": {"EXPERIMENT": "_testing_experiment", "JOB_SOURCE": "experiment_profile/1"},
            "options": {
                "target": 11.0,
            },
            "config_overrides": [],
        }


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_expression_in_common_also_works_with_unit_function(
    mock__load_experiment_profile, active_workers_in_cluster
) -> None:
    job_name = "jobbing"

    for worker in active_workers_in_cluster:
        publish(f"pioreactor/{worker}/_testing_experiment/{job_name}/target", 10, retain=True)

    action = Start(
        hours_elapsed=0, options={"target": "${{unit():jobbing:target + 1}}"}, if_="unit():jobbing:target > 0"
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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", "_testing_experiment")

    assert len(bucket) == len(active_workers_in_cluster)
    for item in bucket:
        assert item.json == {
            "args": [],
            "env": {"EXPERIMENT": "_testing_experiment", "JOB_SOURCE": "experiment_profile/1"},
            "options": {
                "target": 11.0,
            },
            "config_overrides": [],
        }


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_when_action_simple(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
    action = When(
        hours_elapsed=0.0005,
        condition_="${{unit1:od_reading:od1.od > 2.0}}",
        actions=[
            Log(hours_elapsed=0, options=_LogOptions(message="OD exceeded threshold")),
            Start(hours_elapsed=0, options={"target_rpm": 500}),
            Update(hours_elapsed=0.001, options={"target_rpm": 600}),
        ],
    )

    profile = Profile(
        experiment_profile_name="test_when_action_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={"stirring": Job(actions=[action])},
            )
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    # Simulate OD value
    publish(
        f"pioreactor/unit1/{experiment}/od_reading/od1",
        encode(
            RawODReading(
                od=2.5, angle="90", timestamp=current_utc_datetime(), channel="1", ir_led_intensity=80
            )
        ),
        retain=True,
    )

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert len(bucket) == 3
    assert bucket[0].path == f"/api/workers/unit1/experiments/{experiment}/logs"
    assert bucket[1].path == "/unit_api/jobs/run/job_name/stirring"
    assert bucket[2].path == f"/api/workers/unit1/jobs/update/job_name/stirring/experiments/{experiment}"


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_when_action_with_if(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
    action = When(
        hours_elapsed=0.0005,
        if_="1 == 1",
        condition_="${{unit1:od_reading:od1.od > 2.0}}",
        actions=[
            Start(hours_elapsed=0, options={"target_rpm": 500}),
            Update(hours_elapsed=0.001, options={"target_rpm": 600}),
        ],
    )

    profile = Profile(
        experiment_profile_name="test_when_action_with_if_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={"stirring": Job(actions=[action])},
            )
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    # Simulate OD value
    publish(
        f"pioreactor/unit1/{experiment}/od_reading/od1",
        encode(
            RawODReading(
                od=2.5, angle="90", timestamp=current_utc_datetime(), channel="1", ir_led_intensity=80
            )
        ),
        retain=True,
    )

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert len(bucket) == 2
    assert bucket[0].path == "/unit_api/jobs/run/job_name/stirring"
    assert (
        bucket[1].path == "/api/workers/unit1/jobs/update/job_name/stirring/experiments/_testing_experiment"
    )


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_when_action_condition_eventually_met(
    mock__load_experiment_profile,
) -> None:
    experiment = "_testing_experiment"

    when = When(
        hours_elapsed=0.00,
        condition_="${{unit1:stirring:target_rpm > 800}}",
        actions=[
            Update(hours_elapsed=0, options={"target_rpm": 200}),
        ],
    )
    update = Update(hours_elapsed=0.002, options={"target_rpm": 1000})

    profile = Profile(
        experiment_profile_name="test_when_action_condition_not_met_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={"stirring": Job(actions=[when, update])},
            )
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    actions = []

    def collect_actions(msg):
        if msg.payload:
            actions.append(float(msg.payload.decode()))

    subscribe_and_callback(
        collect_actions,
        [f"pioreactor/unit1/{experiment}/stirring/target_rpm"],
        allow_retained=False,
    )

    with capture_requests():
        with start_stirring(target_rpm=500, unit="unit1", experiment=experiment, use_rpm=True):
            execute_experiment_profile("profile.yaml", experiment)

    assert actions == [500, 1000, 200]


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_when_action_nested(
    mock__load_experiment_profile,
) -> None:
    experiment = "_testing_experiment"

    when_inner = When(
        hours_elapsed=0.0001,
        condition_="${{unit1:stirring:target_rpm <= 200}}",
        actions=[
            Update(hours_elapsed=0, options={"target_rpm": 400}),
        ],
    )

    when_outer = When(
        hours_elapsed=0.0,
        condition_="${{unit1:stirring:target_rpm > 800}}",
        actions=[Update(hours_elapsed=0, options={"target_rpm": 200}), when_inner],
    )
    update = Update(hours_elapsed=0.001, options={"target_rpm": 1000})

    profile = Profile(
        experiment_profile_name="test_when_action_condition_not_met_profile",
        plugins=[],
        pioreactors={
            "unit1": PioreactorSpecificBlock(
                jobs={"stirring": Job(actions=[when_outer, update])},
            )
        },
        metadata=Metadata(author="test_author"),
    )

    mock__load_experiment_profile.return_value = profile

    actions = []

    def collect_actions(msg):
        if msg.payload:
            actions.append(float(msg.payload.decode()))

    subscribe_and_callback(
        collect_actions,
        [f"pioreactor/unit1/{experiment}/stirring/target_rpm"],
        allow_retained=False,
    )

    with capture_requests():
        with start_stirring(target_rpm=500, unit="unit1", experiment=experiment, use_rpm=True):
            execute_experiment_profile("profile.yaml", experiment)

    assert actions == [500, 1000, 200, 400]


def test_profiles_in_github_repo() -> None:
    from pioreactor.mureq import get

    # Set the API endpoint URL
    owner = "Pioreactor"
    repo = "experiment_profile_examples"
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"

    response = get(api_url)
    try:
        response.raise_for_status()
    except HTTPErrorStatus as e:
        # raise HTTPErrorStatus(f"HTTP error: Failed to fetch repository contents from {api_url}: saw {str(e)}")
        raise e

    # Check for YAML files
    yaml_files = [
        file for file in response.json() if (file["name"].endswith(".yaml") or file["name"].endswith(".yml"))
    ]

    # Print the list of YAML files
    for file in yaml_files:
        content = get(file["download_url"]).content
        profile = decode(content, type=Profile)
        assert _verify_experiment_profile(profile)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_api_requests_are_made(
    mock__load_experiment_profile,
) -> None:
    experiment = "_testing_experiment"

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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert len(bucket) == 5
    assert bucket[0].path == f"/api/experiments/{experiment}/unit_labels"
    assert bucket[1].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/job1"
    assert bucket[2].url == "http://unit2.local:4999/unit_api/jobs/run/job_name/job1"
    assert bucket[3].url == "http://unit1.local:4999/unit_api/jobs/run/job_name/job2"
    assert bucket[4].path == f"/api/workers/unit1/jobs/stop/job_name/job2/experiments/{experiment}"


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_plugin_version_checks(
    mock__load_experiment_profile,
) -> None:
    experiment = "_testing_experiment"

    profile_with_okay_plugins = Profile(
        experiment_profile_name="test_profile",
        plugins=[Plugin(name="my-example-plugin", version=">=0.1.0")],  # this plugin is locally present in CI
        common=CommonBlock(jobs={}),
        pioreactors={},
        metadata=Metadata(author="test_author"),
    )
    mock__load_experiment_profile.return_value = profile_with_okay_plugins
    execute_experiment_profile("profile.yaml", experiment)

    profile_with_wrong_version = Profile(
        experiment_profile_name="test_profile",
        plugins=[
            Plugin(name="my-example-plugin", version="<=0.1.0")
        ],  # this plugin is locally present in CI, but version 0.2.0
        common=CommonBlock(jobs={}),
        pioreactors={},
        metadata=Metadata(author="test_author"),
    )
    mock__load_experiment_profile.return_value = profile_with_wrong_version
    with pytest.raises(ImportError):
        execute_experiment_profile("profile.yaml", experiment)

    profile_with_missing_package = Profile(
        experiment_profile_name="test_profile",
        plugins=[Plugin(name="doesnt-exist", version="<=0.1.0")],
        common=CommonBlock(jobs={}),
        pioreactors={},
        metadata=Metadata(author="test_author"),
    )
    mock__load_experiment_profile.return_value = profile_with_missing_package
    with pytest.raises(ImportError):
        execute_experiment_profile("profile.yaml", experiment)

    profile_with_nontrivial_version = Profile(
        experiment_profile_name="test_profile",
        plugins=[
            Plugin(name="my-example-plugin", version="<=0.15.1"),
            Plugin(name="my-example-plugin", version=">=0.0.1"),
            Plugin(name="my-example-plugin", version="<=1.0.1"),
        ],
        common=CommonBlock(jobs={}),
        pioreactors={},
        metadata=Metadata(author="test_author"),
    )
    mock__load_experiment_profile.return_value = profile_with_nontrivial_version
    execute_experiment_profile("profile.yaml", experiment)


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_repeat_actions_can_fail_syntax(mock__load_experiment_profile) -> None:
    repeat_num = 6
    repeat_every_hours = 0.001
    start = Start(hours_elapsed=0)
    repeat = Repeat(
        hours_elapsed=0,
        repeat_every_hours=repeat_every_hours,
        max_hours=repeat_every_hours * repeat_num,
        actions=[Update(hours_elapsed=0.0, if_=r"${wrong syntax}", options={"setting": "1"})],
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

    with pytest.raises(SyntaxError):
        # This should raise a SyntaxError because of the invalid if_ syntax
        execute_experiment_profile("profile.yaml", "_testing_experiment")


@patch("pioreactor.actions.leader.experiment_profile._load_experiment_profile")
def test_execute_experiment_profile_with_config_overrides(mock__load_experiment_profile) -> None:
    experiment = "_testing_experiment"
    unit = "unit1"
    job_name = "jobbing"
    publish(f"pioreactor/{unit}/{experiment}/{job_name}/target", 10, retain=True)

    action = Start(
        hours_elapsed=0,
        options={"target": "${{unit1:jobbing:target + 1}}", "dont_eval": "1.0 + 1.0"},
        config_overrides={"option1": "value1", "option2": "value2"},
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

    with capture_requests() as bucket:
        execute_experiment_profile("profile.yaml", experiment)

    assert bucket[0].json == {
        "options": {"target": 11.0, "dont_eval": "1.0 + 1.0"},
        "env": {"EXPERIMENT": "_testing_experiment", "JOB_SOURCE": "experiment_profile/1"},
        "args": [],
        "config_overrides": [
            ["jobbing.config", "option1", "value1"],
            ["jobbing.config", "option2", "value2"],
        ],
    }
