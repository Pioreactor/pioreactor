# -*- coding: utf-8 -*-
from pioreactor.experiment_profiles.profile_struct import CommonBlock
from pioreactor.experiment_profiles.profile_struct import Job
from pioreactor.experiment_profiles.profile_struct import Metadata
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.experiment_profiles.profile_struct import Repeat
from pioreactor.experiment_profiles.profile_struct import Start
from pioreactor.experiment_profiles.profile_struct import Update
from pioreactor.experiment_profiles.validate import validate_profile


def test_validate_profile_returns_error_diagnostic_for_invalid_expression() -> None:
    profile = Profile(
        experiment_profile_name="test_profile",
        metadata=Metadata(author="test_author"),
        common=CommonBlock(
            jobs={
                "stirring": Job(
                    actions=[
                        Start(hours_elapsed=0.0, if_="1 % 1 and "),
                    ]
                )
            }
        ),
    )

    result = validate_profile(profile)

    assert result.ok is False
    assert result.diagnostics[0].severity == "error"
    assert result.diagnostics[0].code == "expression.syntax"
    assert result.diagnostics[0].path == "common.jobs.stirring.actions[0].if"


def test_validate_profile_warns_when_repeat_action_exceeds_cycle_time() -> None:
    profile = Profile(
        experiment_profile_name="test_profile",
        metadata=Metadata(author="test_author"),
        common=CommonBlock(
            jobs={
                "stirring": Job(
                    actions=[
                        Repeat(
                            t="0s",
                            every="1s",
                            actions=[
                                Update(t="2s", options={"target_rpm": 500}),
                            ],
                        )
                    ]
                )
            }
        ),
    )

    result = validate_profile(profile)

    assert result.ok is True
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity == "warning"
    assert result.diagnostics[0].code == "repeat.unreachable_action"
    assert result.diagnostics[0].path == "common.jobs.stirring.actions[0].actions[0].t"


def test_validate_profile_errors_when_both_t_and_hours_elapsed_are_set() -> None:
    profile = Profile(
        experiment_profile_name="test_profile",
        metadata=Metadata(author="test_author"),
        common=CommonBlock(
            jobs={
                "stirring": Job(
                    actions=[
                        Start(hours_elapsed=1.0, t="1h"),
                    ]
                )
            }
        ),
    )

    result = validate_profile(profile)

    assert result.ok is False
    assert result.diagnostics[0].severity == "error"
    assert result.diagnostics[0].code == "action.time.conflict"
    assert result.diagnostics[0].path == "common.jobs.stirring.actions[0]"
