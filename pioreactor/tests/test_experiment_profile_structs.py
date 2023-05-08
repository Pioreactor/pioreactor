# -*- coding: utf-8 -*-
from __future__ import annotations

from msgspec.yaml import decode

from pioreactor.experiment_profiles import structs


def test_simple():
    file = """
experiment_name: plugin_version_example

metadata:
  author: Jane Doe
  description: An experiment using plugins with minimum version requirements

plugins:
  - name: dosing_plugin
    version: ">=1.2.0"
  - name: temperature_control_plugin
    version: ">=0.9.5"

aliases:
  worker1: hot
  worker2: cold

global_jobs:
  od_reading:
    actions:
      - type: start
        duration: 1.0
      - type: stop
        duration: 5.0

pioreactors:
  hot:
    jobs:
      stirring:
        actions:
          - type: start
            duration: 0.5
            parameters:
              target_rpm: 200.0
          - type: stop
            duration: 4.0
  cold:
    jobs:
      stirring:
        actions:
          - type: start
            duration: 1.5
            parameters:
              target_rpm: 250.0
          - type: stop
            duration: 6.0
"""
    assert decode(file, type=structs.Profile) is not None


def test_complex():
    file = """
experiment_name: multi_jobs_dependencies

metadata:
  author: John Doe
  description: Multiple jobs with dependencies, aliases, and plugin requirements in bioreactors
  organism_used: yeast

plugins:
  - name: dosing_plugin
    version: ">=1.2.0"

aliases:
  bioreactor_A: BR-001
  bioreactor_B: BR-002

global_jobs:
  od_reading:
    actions:
      - type: start
        duration: 0.5
      - type: pause
        duration: 2.0
      - type: resume
        duration: 2.5
      - type: stop
        duration: 5.0

pioreactors:
  bioreactor_A:
    jobs:
      stirring:
        actions:
          - type: start
            duration: 0.0
            parameters:
              target_rpm: 200.0
          - type: update
            duration: 1.0
            parameters:
               target_rpm: 250.0
          - type: stop
            duration: 5.0
      dosing_control:
        actions:
          - type: start
            duration: 1.0
            parameters:
              automation_name: glucose_dosing
              glucose_rate: 5
          - type: stop
            duration: 5.0
  bioreactor_B:
    jobs:
      stirring:
        actions:
          - type: start
            duration: 0.0
            parameters:
              target_rpm: 250.0
          - type: update
            duration: 2.0
            parameters:
              target_rpm: 300.0
          - type: stop
            duration: 5.0
      dosing_control:
        actions:
          - type: start
            duration: 1.0
            parameters:
              automation_name: nitrogen_dosing
              nitrogen_rate: 10
          - type: stop
            duration: 5.0
"""
    assert decode(file, type=structs.Profile) is not None
