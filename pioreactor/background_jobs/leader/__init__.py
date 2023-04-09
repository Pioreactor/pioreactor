# -*- coding: utf-8 -*-
"""
A few notes about leader background jobs

1. They should and shouldn't be tied to an experiment. For example, because they use BackgroundJob,
they're settings, status, etc. are tied to an experiment. However, there is no use case so far of a leader needing to know
about the latest_experiment¹


¹ The one use case I can think of is clearing the dashboard time series upon a new experiment starts, but maybe
the leader will partition based on experiment name too, and write <time_series>_<experiment>.json that the dashboard
can read.

"""
from __future__ import annotations
