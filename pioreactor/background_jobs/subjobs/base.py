# -*- coding: utf-8 -*-
from pioreactor.background_jobs.base import BackgroundJob


class BackgroundSubJob(BackgroundJob):
    # don't listen for signal handlers - parents take care of disconnecting us. But we _must_ be a child.

    def __init__(self, *args, parent=None, **kwargs):
        super(BackgroundSubJob, self).__init__(*args, **kwargs)
        self.parent = parent

    def ready(self):
        self.state = self.READY
        try:
            self.on_ready()
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
        self.logger.debug("Ready.")  # don't post to info...

    def set_up_exit_protocol(self):
        # NOOP: subjobs don't exit from python, parents do.
        return

    def on_mqtt_disconnect(self):
        self.logger.debug("Disconnected from MQTT")
        return
