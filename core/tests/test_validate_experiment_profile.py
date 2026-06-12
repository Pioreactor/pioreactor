# -*- coding: utf-8 -*-
from pathlib import Path

from msgspec.yaml import decode as yaml_decode
from pioreactor.experiment_profiles.profile_struct import CommonBlock
from pioreactor.experiment_profiles.profile_struct import Job
from pioreactor.experiment_profiles.profile_struct import Metadata
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.experiment_profiles.profile_struct import Repeat
from pioreactor.experiment_profiles.profile_struct import Start
from pioreactor.experiment_profiles.profile_struct import Update
from pioreactor.experiment_profiles.validate import validate_profile


def test_shared_example_experiment_profiles_are_valid() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    profiles_dir = repo_root / "packaging" / "shared-assets" / "pioreactor" / "experiment_profiles"

    profile_files = sorted(profiles_dir.glob("*.y*ml"))
    assert profile_files

    for profile_file in profile_files:
        profile = yaml_decode(profile_file.read_bytes(), type=Profile)
        result = validate_profile(profile)
        assert result.ok, f"{profile_file}: {result.diagnostics}"


def test_validate_profile_returns_error_diagnostic_for_invalid_expression() -> None:
    profile = Profile(
        experiment_profile_name="test_profile",
        metadata=Metadata(author="test_author"),
        common=CommonBlock(
            jobs={
                "stirring": Job(
                    actions=[
                        Start(hours_elapsed=0.0, if_="1 +"),
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


def test_validate_profile_checks_all_expression_fields_with_full_parser() -> None:
    profile = yaml_decode(
        b"""
experiment_profile_name: test_profile
common:
  jobs:
    stirring:
      actions:
        - type: start
          t: 0s
          if: 1 +
        - type: repeat
          t: 0s
          every: 1h
          while: 1 +
          actions:
            - type: start
              t: 0s
        - type: when
          t: 0s
          condition: 1 +
          actions:
            - type: start
              t: 0s
        - type: when
          t: 0s
          wait_until: 1 +
          actions:
            - type: start
              t: 0s
        - type: start
          t: 0s
          options:
            target_rpm: "${{ 1 + }}"
        - type: log
          t: 0s
          options:
            message: "value ${{ 1 + }}"
""",
        type=Profile,
    )

    result = validate_profile(profile)

    assert result.ok is False
    assert {
        diagnostic.path for diagnostic in result.diagnostics if diagnostic.code == "expression.syntax"
    } == {
        "common.jobs.stirring.actions[0].if",
        "common.jobs.stirring.actions[1].while",
        "common.jobs.stirring.actions[2].condition",
        "common.jobs.stirring.actions[3].wait_until",
        "common.jobs.stirring.actions[4].options.target_rpm",
        "common.jobs.stirring.actions[5].options.message",
    }


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
