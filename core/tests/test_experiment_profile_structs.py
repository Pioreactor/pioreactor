# -*- coding: utf-8 -*-
from __future__ import annotations

import msgspec
import pytest
from msgspec import DecodeError
from msgspec.yaml import decode
from pioreactor.experiment_profiles import profile_struct as structs


def test_minimal() -> None:
    file = """
experiment_profile_name: minimal
"""
    assert decode(file, type=structs.Profile) is not None


def test_simple1() -> None:
    file = """
experiment_profile_name: demo_stirring_example

metadata:
  author: Cam Davidson-Pilon
  description: A simple profile to start stirring in your Pioreactor(s), update RPM at 90 seconds, and turn off after 180 seconds.

common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 0.0
          options:
            target_rpm: 400.0
        - type: update
          hours_elapsed: 0.025
          options:
            target_rpm: 800.0
        - type: stop
          hours_elapsed: 0.05
"""
    assert decode(file, type=structs.Profile) is not None


def test_config_overrides_in_start() -> None:
    file = """
experiment_profile_name: demo_stirring_example

metadata:
  author: Cam Davidson-Pilon
  description: A simple profile to start stirring in your Pioreactor(s), update RPM at 90 seconds, and turn off after 180 seconds.

common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 0.0
          config_overrides:
            initial_target_rpm: 400.0
            initial_duty_cycle: 60
        - type: stop
          hours_elapsed: 0.05
"""
    assert decode(file, type=structs.Profile) is not None


def test_simple2() -> None:
    file = """
experiment_profile_name: plugin_version_example

metadata:
  author: Jane Doe
  description: An experiment using plugins with minimum version requirements

plugins:
  - name: dosing_plugin
    version: ">=1.2.0"
  - name: temperature_control_plugin
    version: ">=0.9.5"

common:
  jobs:
    od_reading:
      actions:
        - type: start
          hours_elapsed: 1.0
        - type: stop
          hours_elapsed: 5.0

pioreactors:
  worker1:
    label: hot
    jobs:
      stirring:
        actions:
          - type: start
            hours_elapsed: 0.5
            options:
              target_rpm: 200.0
          - type: stop
            hours_elapsed: 4.0
  worker2:
    label: cold
    jobs:
      stirring:
        actions:
          - type: start
            hours_elapsed: 1.5
            options:
              target_rpm: 250.0
          - type: stop
            hours_elapsed: 6.0
"""
    assert decode(file, type=structs.Profile) is not None


def test_simple3() -> None:
    file = """
experiment_profile_name: simple_stirring_example

metadata:
  author: John Doe
  description: A simple example of a stirring job in a single pioreactor

common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 0.0
          options:
            target_rpm: 200.0
        - type: stop
          hours_elapsed: 2.0

pioreactors:
  reactor_1:
    label: PR-001
    jobs: {}
"""
    assert decode(file, type=structs.Profile) is not None


def test_complex() -> None:
    file = """
experiment_profile_name: complex_example

metadata:
  author: Cam Davidson-Pilon
  description: A more complex profile to start stirring, heating, and (later) od_reading and growth_rate_calculating.

common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 0.0
          options:
            target_rpm: 400.0
    temperature_automation:
      actions:
        - type: start
          hours_elapsed: 0.0
          options:
            automation_name: thermostat
            target_temperature: 30
    od_reading:
      actions:
        - type: start
          hours_elapsed: 0.25
    growth_rate_calculating:
      actions:
        - type: start
          hours_elapsed: 0.33
"""
    assert decode(file, type=structs.Profile) is not None


def test_complex2() -> None:
    file = """
experiment_profile_name: multi_bioreactor_complex

metadata:
  author: Jane Doe
  description: Complex experiment with multiple jobs and bioreactors

common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 0.0
          options:
            target_rpm: 200.0
        - type: stop
          hours_elapsed: 4.0
    od_reading:
      actions:
        - type: start
          hours_elapsed: 0.0
        - type: stop
          hours_elapsed: 4.0
    growth_rate_calculating:
      actions:
        - type: start
          hours_elapsed: 0.5
        - type: stop
          hours_elapsed: 3.5

pioreactors:
  bioreactor_A:
    jobs:
      dosing_automation:
        actions:
          - type: start
            hours_elapsed: 1.0
            options:
              automation_name: turbidostat
              volume: 1.0
              target_normalized_od: 5.0
          - type: stop
            hours_elapsed: 3.0
"""
    assert decode(file, type=structs.Profile) is not None


def test_complex3() -> None:
    file = """
experiment_profile_name: multi_bioreactor_very_complex

metadata:
  author: Alex Doe
  description: Very complex experiment with multiple jobs and bioreactors, different jobs on different bioreactors

inputs:
  dummy: 1
  dummy_truth: 2

common:
  jobs:
    stirring:
      actions:
        - type: start
          if: ${{dummy > 0}}
          hours_elapsed: 0.0
          options:
            target_rpm: 200.0
        - type: stop
          hours_elapsed: 4.0
    od_reading:
      actions:
        - type: start
          hours_elapsed: 0.0
        - type: stop
          hours_elapsed: 4.0

pioreactors:
  bioreactor_A:
    label: BR-001
    jobs:
      dosing_automation:
        actions:
          - type: start
            hours_elapsed: 1.0
            options:
              automation_name: chemostat
              volume: 1.0
              duration: 10
          - type: stop
            hours_elapsed: 3.0
  bioreactor_B:
    label: BR-002
    jobs:
      growth_rate_calculating:
        actions:
          - type: start
            hours_elapsed: 0.5
          - type: stop
            hours_elapsed: 3.5
      add_media:
        actions:
          - type: start
            hours_elapsed: 2.0
            options:
              volume: 10.0
          - type: stop
            hours_elapsed: 2.5
"""
    assert decode(file, type=structs.Profile) is not None


def test_log() -> None:
    file = """
experiment_profile_name: demo_stirring_example

metadata:
  author: Cam Davidson-Pilon
  description: A simple profile to start stirring in your Pioreactor(s), update RPM at 90 seconds, and turn off after 180 seconds.

common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 0.0
          options:
            target_rpm: 400.0
        - type: log
          hours_elapsed: 0.025
          options:
            message: "log {unit}"
        - type: stop
          hours_elapsed: 0.05

pioreactors:
    bioreactor1:
      jobs:
        od_reading:
          actions:
            - type: log
              hours_elapsed: 0.01
              options:
                message: "log {unit} and {job} and {experiment}"

"""
    assert decode(file, type=structs.Profile) is not None


def test_fails_on_extra_top_level_field() -> None:
    # common mistake
    file = """
experiment_profile_name: demo_of_logging

metadata:
  author: Cam Davidson-Pilon
  description: A  profile to demonstrate logging, start stirring in your Pioreactor(s), update RPM at 90 seconds, and turn off after 180 seconds.

worker1:
  jobs:
    od_reading:
      actions:
        - type: log
          hours_elapsed: 0.01
          options:
            message: "Hello {unit} and {job} and {experiment}"
    """
    with pytest.raises(msgspec.ValidationError):
        decode(file, type=structs.Profile)


def test_fails_on_adding_options_where_they_shouldnt_be() -> None:
    file = """
experiment_profile_name: demo_of_logging

metadata:
  author: Cam Davidson-Pilon
  description: A  profile to demonstrate logging, start stirring in your Pioreactor(s), update RPM at 90 seconds, and turn off after 180 seconds.

common:
  jobs:
    stirring:
      actions:
        - type: start
          hours_elapsed: 0.0
          options:
            target_rpm: 400.0
        - type: update
          hours_elapsed: 0.025
          options:
            target_rpm: 800.0
        - type: stop
          hours_elapsed: 0.05
          options: # stop doesn't have options
              this_fails: 0

    """
    with pytest.raises(msgspec.ValidationError, match="Object contains unknown field `options`"):
        decode(file, type=structs.Profile)


def test_if_statement() -> None:
    file = """
experiment_profile_name: simple_stirring_example

metadata:
  author: John Doe
  description: A simple example of a stirring job in a single pioreactor

pioreactors:
  reactor_1:
    jobs:
      stirring:
        actions:
          - type: start
            if: "True"
            hours_elapsed: 0.0
            options:
              target_rpm: 200.0
          - type: stop
            hours_elapsed: 2.0
            if: 1 > 0

"""
    assert decode(file, type=structs.Profile) is not None


def test_repeat_statement() -> None:
    file = """
experiment_profile_name: demo_stirring_repeat

metadata:
  author: Cam Davidson-Pilon
  description: A simple profile that shows of a repeat

pioreactors:
  worker1:
    jobs:
      stirring:
        actions:
          - type: start
            hours_elapsed: 0.0
            options:
              target_rpm: 400.0
          - type: log
            hours_elapsed: 0.001
            options:
              message: "start repeat"
          - type: repeat
            hours_elapsed: 0.001
            while: (1 > 0)
            if: (0 > 0)
            max_hours: 0.010
            repeat_every_hours: 0.002
            actions:
              - type: update
                hours_elapsed: 0.0
                options:
                  target_rpm: 400

    """
    assert decode(file, type=structs.Profile) is not None

    file = """
  experiment_profile_name: demo_stirring_repeat

  metadata:
    author: Cam Davidson-Pilon
    description: A simple profile that shows of a repeat

  pioreactors:
    worker1:
      jobs:
        stirring:
          actions:
            - type: start
              hours_elapsed: 0.0
              options:
                target_rpm: 400.0
            - type: log
              hours_elapsed: 0.001
              options:
                message: "start repeat"
            - type: repeat
              hours_elapsed: 0.001
              max_hours: 0.010
              repeat_every_hours: 0.002
              actions: []
    """
    assert decode(file, type=structs.Profile) is not None


def test_no_repeats_in_repeats() -> None:
    bad_file = """
  experiment_profile_name: demo_stirring_repeat

  metadata:
    author: Cam Davidson-Pilon
    description: A simple profile that shows of a repeat

  pioreactors:
    worker1:
      jobs:
        stirring:
          actions:
            - type: start
              hours_elapsed: 0.0
              options:
                target_rpm: 400.0
            - type: log
              hours_elapsed: 0.001
              options:
                message: "start repeat"
            - type: repeat
              hours_elapsed: 0.001
              while: True
              repeat_every_hours: 0.002
              actions:
                - type: repeat
                  hours_elapsed: 0.001
                  while: True
                  repeat_every_hours: 0.002
                  actions: []
    """
    with pytest.raises(DecodeError):
        decode(bad_file, type=structs.Profile)
