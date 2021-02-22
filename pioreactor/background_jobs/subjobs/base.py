# -*- coding: utf-8 -*-
from pioreactor.background_jobs.base import BackgroundJob


class BackgroundSubJob(BackgroundJob):
    # don't listen for signal handlers - parents take care of disconnecting us. But we _must_ be a child.

    def set_up_disconnect_protocol(self):
        pass

    def disconnected(self):
        # subjobs don't send a USR signal to end the job.

        try:
            # call job specific on_disconnect to clean up subjobs, etc.
            # however, if it fails, nothing below executes, so we don't get a clean
            # disconnect, etc. Hence the `try` block.
            self.on_disconnect()
        except Exception as e:
            self.logger.error(e, exc_info=True)

        # set state to disconnect before disconnecting our pubsub clients.
        self.state = self.DISCONNECTED
        self.logger.info(self.DISCONNECTED)

        # disconnect from the passive subscription threads
        self.pubsub_client.loop_stop()  # takes a second or two.
        self.pubsub_client.disconnect()
