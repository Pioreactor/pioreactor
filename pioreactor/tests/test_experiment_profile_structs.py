# -*- coding: utf-8 -*-
from __future__ import annotations

from msgspec.yaml import decode

from pioreactor.experiment_profiles import profile_struct as structs


def test_smallest():
    file = """
experiment_profile_name: small
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
