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

    def on_mqtt_disconnect(self, rc: int):
        if (
            rc == 0
        ):  # MQTT_ERR_SUCCESS means that the client disconnected using disconnect()
            self.logger.debug("Disconnected successfully from MQTT.")

            # once disconnected, we send a signal to this specific job on the OS.
            # this will unblock the signal.pause() that may be running.
        else:
            # we won't exit, but the client object will try to reconnect
            # Error codes are below, but don't always align
            # https://github.com/eclipse/paho.mqtt.python/blob/42f0b13001cb39aee97c2b60a3b4807314dfcb4d/src/paho/mqtt/client.py#L147
            self.logger.debug(f"Disconnected from MQTT with rc {rc}.")
            return

    def log_state(self, state):
        self.logger.debug(state.capitalize() + ".")

    def check_for_duplicate_process(self):
        # multiple subjobs can run, sometimes - the parents should control this.
        return
