# -*- coding: utf-8 -*-
from __future__ import annotations

from msgspec.yaml import decode

from pioreactor.experiment_profiles import profile_struct as structs


def test_minimal():
    file = """
experiment_profile_name: minimal
"""
    assert decode(file, type=structs.Profile) is not None


def test_simple1():
    file = """
experiment_profile_name: test_simple1

metadata:
  author: Jane Doe
  description:

common:
  od_reading:
    actions:
      - type: start
        hours_elapsed: 1.0
"""
    assert decode(file, type=structs.Profile) is not None


def test_simple2():
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

labels:
  worker1: hot
  worker2: cold

common:
  od_reading:
    actions:
      - type: start
        hours_elapsed: 1.0
      - type: stop
        hours_elapsed: 5.0

pioreactors:
  hot:
    jobs:
      stirring:
        actions:
          - type: start
            hours_elapsed: 0.5
            options:
              target_rpm: 200.0
          - type: stop
            hours_elapsed: 4.0
  cold:
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


def test_simple3():
    file = """
experiment_profile_name: simple_stirring_example

metadata:
  author: John Doe
  description: A simple example of a stirring job in a single pioreactor

aliases:
  reactor_1: PR-001

common:
  stirring:
    actions:
      - type: start
        hours_elapsed: 0.0
        parameters:
          target_rpm: 200.0
      - type: stop
        hours_elapsed: 2.0

pioreactors:
  reactor_1:
    jobs: {}
"""
    assert decode(file, type=structs.Profile) is not None


def test_complex():
    file = """
experiment_profile_name: multi_jobs_dependencies

metadata:
  author: John Doe
  description: Multiple jobs with dependencies, aliases, and plugin requirements in bioreactors
  organism_used: yeast

plugins:
  - name: dosing_plugin
    version: ">=1.2.0"

labels:
  bioreactor_A: BR-001
  bioreactor_B: BR-002

common:
  od_reading:
    actions:
      - type: start
        hours_elapsed: 0.5
      - type: pause
        hours_elapsed: 2.0
      - type: resume
        hours_elapsed: 2.5
      - type: stop
        hours_elapsed: 5.0

pioreactors:
  bioreactor_A:
    jobs:
      stirring:
        actions:
          - type: start
            hours_elapsed: 0.0
            options:
              target_rpm: 200.0
          - type: update
            hours_elapsed: 1.0
            options:
               target_rpm: 250.0
          - type: stop
            hours_elapsed: 5.0
      dosing_control:
        actions:
          - type: start
            hours_elapsed: 1.0
            options:
              automation_name: glucose_dosing
              glucose_rate: 5
          - type: stop
            hours_elapsed: 5.0
  bioreactor_B:
    jobs:
      stirring:
        actions:
          - type: start
            hours_elapsed: 0.0
            options:
              target_rpm: 250.0
          - type: update
            hours_elapsed: 2.0
            options:
              target_rpm: 300.0
          - type: stop
            hours_elapsed: 5.0
      dosing_control:
        actions:
          - type: start
            hours_elapsed: 1.0
            options:
              automation_name: nitrogen_dosing
              nitrogen_rate: 10
          - type: stop
            hours_elapsed: 5.0
"""
    assert decode(file, type=structs.Profile) is not None


def test_complex2():
    file = """
experiment_profile_name: multi_bioreactor_complex

metadata:
  author: Jane Doe
  description: Complex experiment with multiple jobs and bioreactors

aliases:
  bioreactor_A: BR-001
  bioreactor_B: BR-002

common:
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
      dosing_control:
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


def test_complex3():
    file = """
experiment_profile_name: multi_bioreactor_very_complex

metadata:
  author: Alex Doe
  description: Very complex experiment with multiple jobs and bioreactors, different jobs on different bioreactors

aliases:
  bioreactor_A: BR-001
  bioreactor_B: BR-002
  bioreactor_C: BR-003

common:
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

pioreactors:
  bioreactor_A:
    jobs:
      dosing_control:
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
