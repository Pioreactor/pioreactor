# -*- coding: utf-8 -*-
import time
from pioreactor.background_jobs.base import BackgroundJob


class BackgroundSubJob(BackgroundJob):
    # don't listen for signal handlers - parents take care of disconnecting us. But we _must_ be a child.

    def set_up_disconnect_protocol(self):
        pass

    def disconnected(self):
        # subjobs don't send a USR signal to end the job.
        self.state = self.DISCONNECTED

        try:
            # call job specific on_disconnect to clean up subjobs, etc.
            # however, if it fails, nothing below executes, so we don't get a clean
            # disconnect, etc. Hence the `try` block.
            self.on_disconnect()
        except Exception as e:
            self.logger.error(e, exc_info=True)

        time.sleep(0.5)

        # set state to disconnect before disconnecting our pubsub clients.
        self.logger.info(self.DISCONNECTED)

        # disconnect from the passive subscription threads
        self.pubsub_client.disconnect()
        self.pubsub_client.loop_stop()  # takes a second or two.
