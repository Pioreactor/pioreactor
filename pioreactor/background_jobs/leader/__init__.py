# -*- coding: utf-8 -*-
"""
A few notes about leader background jobs

1. The should and shouldn't be tied to an experiment. For example, because they use BackgroundJob,
they're settings, status, etc. are tied to an experiment. However, I often don't want them tied to an
experiment - the user shouldn't need to interact with leader outside of the UI - so who starts the leader jobs?

2. Based on the above, maybe I need a universal experiment name...

"""
