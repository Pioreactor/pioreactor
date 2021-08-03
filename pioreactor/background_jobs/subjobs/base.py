# -*- coding: utf-8 -*-
from pioreactor.background_jobs.base import BackgroundJob


class BackgroundSubJob(BackgroundJob):
    # don't listen for signal handlers - parents take care of disconnecting us. But we _must_ be a child.

    def __init__(self, *args, parent=None, **kwargs):
        super(BackgroundSubJob, self).__init__(*args, **kwargs)
        self.parent = parent

    def set_up_exit_protocol(self):
        # NOOP: subjobs don't exit from python, parents do.
        return

    def on_mqtt_disconnect(self):
        self.logger.debug("Disconnected from MQTT")
        return

    def log_state(self, state):
        self.logger.debug(state.capitalize() + ".")

    def check_for_duplicate_process(self):
        # multiple subjobs can run, sometimes - the parents should control this.
        return
