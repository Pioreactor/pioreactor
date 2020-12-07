# -*- coding: utf-8 -*-
from pioreactor.background_jobs.base import BackgroundJob


class BackgroundSubJob(BackgroundJob):
    # don't listen for signal handlers - parents take care of disconnecting us. But we _must_ be a child,

    def init(self):
        self.state = self.INIT
        self.logger.info(self.INIT)

        # if we re-init (via MQTT, close previous threads)
        for client in self.pubsub_clients:
            client.loop_stop()
            client.disconnect()
        self.pubsub_clients = []

        self.declare_settable_properties_to_broker()
        self.start_general_passive_listeners()

    def disconnected(self):
        # subjobs don't send a USR signal to end the job.

        # call job specific on_disconnect to clean up subjobs, etc.
        self.on_disconnect()

        # disconnect from the passive subscription threads
        for client in self.pubsub_clients:
            client.loop_stop()  # takes a second or two.
            self.logger.debug(self, client.disconnect())

        # set state to disconnect
        self.state = self.DISCONNECTED
        self.logger.info(self.DISCONNECTED)
