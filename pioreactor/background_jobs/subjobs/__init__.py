# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.background_jobs.base import BackgroundJob


class BackgroundSubJob(BackgroundJob):
    # don't listen for signal handlers - parents take care of disconnecting us. But we _must_ be a child.

    def _set_up_exit_protocol(self):
        # NOOP: subjobs don't exit from python, parents do.
        return

    def _log_state(self, state):
        self.logger.debug(state.capitalize() + ".")

    def _check_for_duplicate_process(self):
        # multiple subjobs can run - the parents should control if it's not allowed.
        return
